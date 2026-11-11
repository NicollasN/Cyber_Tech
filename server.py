import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file
from waitress import serve
from werkzeug.exceptions import HTTPException

from BackEnd import main as backend


ROOT_DIR = backend.ROOT_DIR
FRONTEND_DIR = backend.FRONTEND_DIR
IMAGE_DIR = ROOT_DIR / "Imagens"


def read_json_payload() -> dict[str, Any]:
    content_length = request.content_length
    if content_length is not None and (
        content_length <= 0 or content_length > backend.MAX_REQUEST_SIZE
    ):
        raise ValueError("O tamanho dos dados enviados é inválido.")

    raw_payload = request.get_data(cache=False)
    if not raw_payload or len(raw_payload) > backend.MAX_REQUEST_SIZE:
        raise ValueError("O tamanho dos dados enviados é inválido.")

    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Envie os dados em formato JSON válido.") from None
    if not isinstance(payload, dict):
        raise ValueError("Envie os dados em formato JSON válido.")
    return payload


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = backend.MAX_REQUEST_SIZE
    backend.initialize_database()

    @app.after_request
    def add_response_headers(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        status_code = error.code or 500
        if error.code == 413:
            message = "O tamanho dos dados enviados é inválido."
        elif error.code == 405 and request.path.startswith("/api/"):
            message = "Endereço não encontrado."
            status_code = 404
        elif error.code == 405:
            message = "Método não permitido."
        elif error.code == 404 and request.path.startswith("/api/"):
            message = "Endereço não encontrado."
        else:
            message = "Página não encontrada."
        return jsonify(error=message), status_code

    def is_authenticated() -> bool:
        session_id = request.cookies.get(backend.SESSION_COOKIE)
        if session_id is None:
            return False
        expires_at = backend._sessions.get(session_id)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            backend._sessions.pop(session_id, None)
            return False
        return True

    def unauthorized_response() -> tuple[Response, int]:
        return (
            jsonify(error="Entre na sua conta administrativa para continuar."),
            401,
        )

    def static_file(file_path: Path) -> Response:
        response = send_file(file_path)
        response.headers["Content-Type"] = (
            f"{response.mimetype}; charset=utf-8"
            if response.mimetype and response.mimetype.startswith("text/")
            else response.mimetype or "application/octet-stream"
        )
        return response

    @app.get("/")
    def home() -> Response:
        return static_file(FRONTEND_DIR / "index.html")

    @app.get("/admin")
    def admin() -> Response:
        return static_file(FRONTEND_DIR / "admin.html")

    @app.get("/api/products")
    def list_products() -> tuple[Response, int] | Response:
        try:
            with backend.connect_database() as connection:
                rows = connection.execute(
                    """
                    SELECT id, name, category, description, price, tag, image, affiliate_url
                    FROM products ORDER BY id DESC
                    """
                ).fetchall()
        except sqlite3.Error:
            app.logger.exception("Não foi possível listar os produtos.")
            return jsonify(error="Não foi possível carregar os produtos."), 500
        return jsonify(products=[backend.product_as_json(row) for row in rows])

    @app.get("/api/session")
    def session_status() -> Response:
        return jsonify(authenticated=is_authenticated())

    @app.post("/api/login")
    def login() -> tuple[Response, int] | Response:
        try:
            payload = read_json_payload()
        except ValueError as error:
            return jsonify(error=str(error)), 400

        email = payload.get("email")
        password = payload.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            return jsonify(error="Informe seu e-mail e sua senha."), 400

        email_matches = hmac.compare_digest(
            email.strip().casefold().encode("utf-8"),
            backend.ADMIN_EMAIL.encode("utf-8"),
        )
        password_matches = hmac.compare_digest(
            password.encode("utf-8"), backend.ADMIN_PASSWORD.encode("utf-8")
        )
        if not backend.ADMIN_EMAIL or not backend.ADMIN_PASSWORD or not (
            email_matches and password_matches
        ):
            return jsonify(error="E-mail ou senha incorretos."), 401

        session_id = secrets.token_urlsafe(32)
        backend._sessions[session_id] = time.time() + backend.SESSION_TTL_SECONDS
        response = jsonify(authenticated=True)
        response.set_cookie(
            backend.SESSION_COOKIE,
            session_id,
            max_age=backend.SESSION_TTL_SECONDS,
            httponly=True,
            secure=backend.COOKIE_SECURE,
            samesite="Strict",
            path="/",
        )
        return response

    @app.post("/api/logout")
    def logout() -> Response:
        session_id = request.cookies.get(backend.SESSION_COOKIE)
        if session_id is not None:
            backend._sessions.pop(session_id, None)
        response = jsonify(authenticated=False)
        response.delete_cookie(
            backend.SESSION_COOKIE,
            httponly=True,
            secure=backend.COOKIE_SECURE,
            samesite="Strict",
            path="/",
        )
        return response

    @app.post("/api/products")
    def create_product() -> tuple[Response, int] | Response:
        if not is_authenticated():
            return unauthorized_response()
        try:
            product = backend.validate_product(read_json_payload())
            with backend.connect_database() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO products
                        (name, category, description, price, tag, image, affiliate_url, stock)
                    VALUES
                        (:name, :category, :description, :price, :tag, :image, :affiliate_url, 0)
                    """,
                    product,
                )
                row = connection.execute(
                    """
                    SELECT id, name, category, description, price, tag, image, affiliate_url
                    FROM products WHERE id = ?
                    """,
                    (cursor.lastrowid,),
                ).fetchone()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except sqlite3.Error:
            app.logger.exception("Não foi possível criar o produto.")
            return jsonify(error="Não foi possível salvar o produto."), 500
        return jsonify(product=backend.product_as_json(row)), 201

    @app.put("/api/products/<int:product_id>")
    def update_product(product_id: int) -> tuple[Response, int] | Response:
        if not is_authenticated():
            return unauthorized_response()
        try:
            product = backend.validate_product(read_json_payload())
            with backend.connect_database() as connection:
                cursor = connection.execute(
                    """
                    UPDATE products
                    SET name = :name, category = :category, description = :description,
                        price = :price, tag = :tag, image = :image,
                        affiliate_url = :affiliate_url
                    WHERE id = :id
                    """,
                    {**product, "id": product_id},
                )
                if cursor.rowcount == 0:
                    return jsonify(error="Produto não encontrado."), 404
                row = connection.execute(
                    """
                    SELECT id, name, category, description, price, tag, image, affiliate_url
                    FROM products WHERE id = ?
                    """,
                    (product_id,),
                ).fetchone()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except sqlite3.Error:
            app.logger.exception("Não foi possível atualizar o produto.")
            return jsonify(error="Não foi possível salvar o produto."), 500
        return jsonify(product=backend.product_as_json(row))

    @app.delete("/api/products/<int:product_id>")
    def delete_product(product_id: int) -> tuple[Response, int] | Response:
        if not is_authenticated():
            return unauthorized_response()
        try:
            with backend.connect_database() as connection:
                cursor = connection.execute(
                    "DELETE FROM products WHERE id = ?", (product_id,)
                )
        except sqlite3.Error:
            app.logger.exception("Não foi possível remover o produto.")
            return jsonify(error="Não foi possível remover o produto."), 500
        if cursor.rowcount == 0:
            return jsonify(error="Produto não encontrado."), 404
        return jsonify(message="Produto removido.")

    @app.get("/<path:requested_path>")
    def serve_static_file(requested_path: str) -> tuple[Response, int] | Response:
        relative_path = requested_path.lstrip("/")
        frontend_file = (FRONTEND_DIR / relative_path).resolve()
        image_file = (ROOT_DIR / relative_path).resolve()
        file_path = frontend_file if frontend_file.is_file() else image_file
        allowed_roots = (FRONTEND_DIR.resolve(), IMAGE_DIR.resolve())
        if (
            not file_path.is_file()
            or not any(file_path.is_relative_to(root) for root in allowed_roots)
        ):
            if request.path.startswith("/api/"):
                return jsonify(error="Endereço não encontrado."), 404
            return jsonify(error="Página não encontrada."), 404
        return static_file(file_path)

    return app


app = create_app()


if __name__ == "__main__":
    if not backend.ADMIN_EMAIL or not backend.ADMIN_PASSWORD:
        raise SystemExit(
            "Configure ADMIN_EMAIL e ADMIN_PASSWORD no arquivo .env antes de iniciar."
        )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    serve(app, host=host, port=port)
