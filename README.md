# Cyber Tech

## Iniciar o site e o painel

Na pasta do projeto, execute:

```powershell
.\tech\Scripts\python.exe .\BackEnd\main.py
```

Abra `http://127.0.0.1:8000` para visitar a loja ou `http://127.0.0.1:8000/admin`
para gerenciar os produtos. O servidor usa o SQLite em `database.db` e inicia
com os seis produtos atuais da vitrine.

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
