import hmac
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlsplit


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "FrontEnd"
DATABASE_PATH = ROOT_DIR / "database.db"
SESSION_COOKIE = "ct_admin_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_REQUEST_SIZE = 64 * 1024
ALLOWED_CATEGORIES = {"celulares", "notebooks", "consoles", "acessorios"}
_sessions: dict[str, float] = {}


def load_environment() -> None:
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_environment()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().casefold()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


@contextmanager
def connect_database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with connect_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(products)")
        }
        new_columns = {
            "tag": "TEXT NOT NULL DEFAULT ''",
            "image": "TEXT NOT NULL DEFAULT ''",
            "affiliate_url": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in new_columns.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE products ADD COLUMN {column} {definition}"
                )

        connection.execute(
            """
            UPDATE products
            SET tag = CASE category
                WHEN 'celulares' THEN 'Smartphone'
                WHEN 'notebooks' THEN 'Computação'
                WHEN 'consoles' THEN 'Console'
                ELSE 'Acessório'
            END
            WHERE tag = ''
            """
        )
        connection.execute(
            """
            UPDATE products SET image = ?
            WHERE image = '' OR image IS NULL
            """,
            (
                "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9"
                "?auto=format&fit=crop&w=900&q=80",
            ),
        )
        connection.execute(
            """
            UPDATE products SET affiliate_url = 'https://www.mercadolivre.com.br/'
            WHERE affiliate_url = '' OR affiliate_url IS NULL
            """
        )

        if connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed_products = [
                (
                    "iPhone 15 Pro Max",
                    "celulares",
                    "Smartphone premium para fotos, vídeos e produtividade.",
                    7499,
                    "Smartphone",
                    "https://images.unsplash.com/photo-1598327105666-5b89351aff97?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
                (
                    "Notebook Gamer Acer Nitro 5",
                    "notebooks",
                    "Performance para jogos, trabalho e criação.",
                    4899,
                    "Performance",
                    "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
                (
                    "PlayStation 5 Slim",
                    "consoles",
                    "Entre na nova geração de jogos.",
                    3899,
                    "Console",
                    "https://images.unsplash.com/photo-1606144042614-b2417e99c4e3?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
                (
                    "Fone JBL Tune 760NC",
                    "acessorios",
                    "Som imersivo para acompanhar a sua rotina.",
                    699,
                    "Áudio",
                    "https://images.unsplash.com/photo-1546435770-a3e426bf472b?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
                (
                    "Smartwatch Amazfit Bip U Pro",
                    "acessorios",
                    "Acompanhe atividades e notificações durante o dia.",
                    499,
                    "Wearable",
                    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
                (
                    "Teclado Mecânico RGB",
                    "acessorios",
                    "Um teclado mecânico para completar o seu setup.",
                    389,
                    "Setup",
                    "https://images.unsplash.com/photo-1511467687858-23d96c32e4ae?auto=format&fit=crop&w=900&q=80",
                    "https://www.mercadolivre.com.br/",
                    0,
                ),
            ]
            connection.executemany(
                """
                INSERT INTO products
                    (name, category, description, price, tag, image, affiliate_url, stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_products,
            )


def product_as_json(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"] or "",
        "price": row["price"],
        "tag": row["tag"],
        "image": row["image"],
        "affiliateUrl": row["affiliate_url"],
    }


def validate_product(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Envie os dados do produto em formato válido.")

    name = payload.get("name")
    category = payload.get("category")
    tag = payload.get("tag")
    description = payload.get("description", "")
    image = payload.get("image")
    affiliate_url = payload.get("affiliateUrl")

    for value, label, maximum in (
        (name, "Nome", 120),
        (category, "Categoria", 40),
        (tag, "Identificação", 40),
        (description, "Descrição", 1000),
        (image, "Imagem", 2048),
        (affiliate_url, "Link de afiliado", 2048),
    ):
        if (
            not isinstance(value, str)
            or len(value) > maximum
            or (label != "Descrição" and not value.strip())
        ):
            raise ValueError(f"{label}: preencha o campo respeitando o limite permitido.")

    name = name.strip()
    category = category.strip()
    tag = tag.strip()
    description = description.strip()
    image = image.strip()
    affiliate_url = affiliate_url.strip()

    if category not in ALLOWED_CATEGORIES:
        raise ValueError("Selecione uma categoria disponível.")

    try:
        price = float(payload.get("price"))
    except (TypeError, ValueError):
        raise ValueError("Informe um preço válido.") from None
    if not math.isfinite(price) or price <= 0:
        raise ValueError("O preço precisa ser maior que zero.")

    image_parts = urlsplit(image)
    local_image = image.startswith("/") and not image.startswith("//") and "\\" not in image
    remote_image = (
        image_parts.scheme == "https"
        and bool(image_parts.netloc)
        and not image_parts.username
        and not image_parts.password
    )
    if not (local_image or remote_image):
        raise ValueError("A imagem precisa ser um caminho local ou um link HTTPS válido.")

    affiliate_parts = urlsplit(affiliate_url)
    if (
        affiliate_parts.scheme != "https"
        or not affiliate_parts.netloc
        or affiliate_parts.username
        or affiliate_parts.password
    ):
        raise ValueError("O link de afiliado precisa ser um endereço HTTPS válido.")

    return {
        "name": name,
        "category": category,
        "tag": tag,
        "description": description,
        "price": price,
        "image": image,
        "affiliate_url": affiliate_url,
    }


class CyberTechHandler(BaseHTTPRequestHandler):
    server_version = "CyberTech"

    def log_message(self, format: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def send_json(self, status: HTTPStatus, body: dict) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Não foi possível ler os dados enviados.") from None
        if content_length <= 0 or content_length > MAX_REQUEST_SIZE:
            raise ValueError("O tamanho dos dados enviados é inválido.")
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Envie os dados em formato JSON válido.") from None
        if not isinstance(payload, dict):
            raise ValueError("Envie os dados em formato JSON válido.")
        return payload

    def is_authenticated(self) -> bool:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return False
        cookie = cookies.get(SESSION_COOKIE)
        if cookie is None:
            return False
        expires_at = _sessions.get(cookie.value)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            _sessions.pop(cookie.value, None)
            return False
        return True

    def require_authentication(self) -> bool:
        if self.is_authenticated():
            return True
        self.send_json(
            HTTPStatus.UNAUTHORIZED,
            {"error": "Entre na sua conta administrativa para continuar."},
        )
        return False

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/products":
            try:
                with connect_database() as connection:
                    rows = connection.execute(
                        """
                        SELECT id, name, category, description, price, tag, image, affiliate_url
                        FROM products ORDER BY id DESC
                        """
                    ).fetchall()
            except sqlite3.Error:
                logging.exception("Não foi possível listar os produtos.")
                self.send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "Não foi possível carregar os produtos."},
                )
                return
            self.send_json(
                HTTPStatus.OK,
                {"products": [product_as_json(row) for row in rows]},
            )
            return

        if path == "/api/session":
            self.send_json(HTTPStatus.OK, {"authenticated": self.is_authenticated()})
            return

        if path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Endereço não encontrado."})
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/login":
            self.login()
            return
        if path == "/api/logout":
            self.logout()
            return
        if path == "/api/products":
            if not self.require_authentication():
                return
            self.create_product()
            return
        if path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Endereço não encontrado."})
            return
        self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Método não permitido."})

    def do_PUT(self) -> None:
        if not self.require_authentication():
            return
        match = re.fullmatch(r"/api/products/(\d+)", urlsplit(self.path).path)
        if match is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Produto não encontrado."})
            return
        self.update_product(int(match.group(1)))

    def do_DELETE(self) -> None:
        if not self.require_authentication():
            return
        match = re.fullmatch(r"/api/products/(\d+)", urlsplit(self.path).path)
        if match is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Produto não encontrado."})
            return
        try:
            with connect_database() as connection:
                cursor = connection.execute(
                    "DELETE FROM products WHERE id = ?", (int(match.group(1)),)
                )
        except sqlite3.Error:
            logging.exception("Não foi possível remover o produto.")
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Não foi possível remover o produto."},
            )
            return
        if cursor.rowcount == 0:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Produto não encontrado."})
            return
        self.send_json(HTTPStatus.OK, {"message": "Produto removido."})

    def login(self) -> None:
        try:
            payload = self.read_json()
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        email = payload.get("email")
        password = payload.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Informe seu e-mail e sua senha."},
            )
            return

        email_matches = hmac.compare_digest(
            email.strip().casefold().encode("utf-8"), ADMIN_EMAIL.encode("utf-8")
        )
        password_matches = hmac.compare_digest(
            password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")
        )
        if not ADMIN_EMAIL or not ADMIN_PASSWORD or not (
            email_matches and password_matches
        ):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "E-mail ou senha incorretos."})
            return

        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = time.time() + SESSION_TTL_SECONDS
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        secure_attribute = "; Secure" if COOKIE_SECURE else ""
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={session_id}; HttpOnly; SameSite=Strict; "
            f"Path=/; Max-Age={SESSION_TTL_SECONDS}{secure_attribute}",
        )
        body = json.dumps({"authenticated": True}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def logout(self) -> None:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            cookies = SimpleCookie()
        cookie = cookies.get(SESSION_COOKIE)
        if cookie is not None:
            _sessions.pop(cookie.value, None)
        secure_attribute = "; Secure" if COOKIE_SECURE else ""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            f"{secure_attribute}",
        )
        body = json.dumps({"authenticated": False}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def create_product(self) -> None:
        try:
            product = validate_product(self.read_json())
            with connect_database() as connection:
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
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except sqlite3.Error:
            logging.exception("Não foi possível criar o produto.")
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Não foi possível salvar o produto."},
            )
            return
        self.send_json(HTTPStatus.CREATED, {"product": product_as_json(row)})

    def update_product(self, product_id: int) -> None:
        try:
            product = validate_product(self.read_json())
            with connect_database() as connection:
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
                    self.send_json(
                        HTTPStatus.NOT_FOUND, {"error": "Produto não encontrado."}
                    )
                    return
                row = connection.execute(
                    """
                    SELECT id, name, category, description, price, tag, image, affiliate_url
                    FROM products WHERE id = ?
                    """,
                    (product_id,),
                ).fetchone()
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except sqlite3.Error:
            logging.exception("Não foi possível atualizar o produto.")
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Não foi possível salvar o produto."},
            )
            return
        self.send_json(HTTPStatus.OK, {"product": product_as_json(row)})

    def serve_static(self, requested_path: str) -> None:
        if requested_path == "/":
            requested_path = "/index.html"
        elif requested_path == "/admin":
            requested_path = "/admin.html"

        relative_path = unquote(requested_path.lstrip("/"))
        frontend_path = (FRONTEND_DIR / relative_path).resolve()
        image_path = (ROOT_DIR / relative_path).resolve()
        file_path = frontend_path if frontend_path.is_file() else image_path
        allowed_roots = (FRONTEND_DIR.resolve(), (ROOT_DIR / "Imagens").resolve())
        if not any(file_path.is_relative_to(root) for root in allowed_roots) or not file_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada."})
            return

        try:
            content = file_path.read_bytes()
        except OSError:
            logging.exception("Não foi possível carregar %s.", file_path)
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Não foi possível carregar esta página."},
            )
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            f"{content_type or 'application/octet-stream'}; charset=utf-8"
            if content_type and content_type.startswith("text/")
            else content_type or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise SystemExit(
            "Configure ADMIN_EMAIL e ADMIN_PASSWORD no arquivo .env antes de iniciar."
        )
    initialize_database()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), CyberTechHandler)
    print(f"Cyber Tech disponível em http://127.0.0.1:{port}")
    print(f"Painel administrativo: http://127.0.0.1:{port}/admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
