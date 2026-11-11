# Cyber Tech

## Iniciar o site e o painel

Instale as dependências e inicie o servidor Flask com Waitress:

```powershell
.\tech\Scripts\python.exe -m pip install -r .\requirements.txt
.\tech\Scripts\python.exe .\server.py
```

Abra `http://127.0.0.1:8000` para visitar a loja ou
`http://127.0.0.1:8000/admin` para gerenciar os produtos. O servidor serve o
front-end e a API no mesmo domínio, usa o SQLite em `database.db` e inicializa
o catálogo se ele ainda estiver vazio.

Para disponibilizar o site em uma hospedagem, configure `HOST=0.0.0.0`, use a
porta definida pelo provedor (variável `PORT`) e ative `COOKIE_SECURE=true`
quando o domínio estiver protegido por HTTPS. O `server.py` usa Waitress, um
servidor WSGI compatível com Windows; `BackEnd/main.py` continua disponível
como servidor HTTP local legado.

O painel permite adicionar, editar, buscar e excluir produtos. As alterações
aparecem imediatamente na loja, e cada produto pode ter seu próprio link de
afiliado. Para novas imagens, use um endereço HTTPS ou um caminho local dentro
da pasta `Imagens`.

## Acesso administrativo

O acesso ao painel usa e-mail e senha. As credenciais ficam em `.env`, são
verificadas pelo servidor e não são incluídas no JavaScript público. O arquivo
`.env` está no `.gitignore`.
`COOKIE_SECURE=false` é apropriado apenas para o servidor local HTTP; em uma
implantação HTTPS, defina `COOKIE_SECURE=true` e configure o host e a porta
adequados. Mantenha esse arquivo privado e use uma senha forte própria antes de
publicar o site.
