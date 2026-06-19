# Argus Follows

Dashboard Flask para acompanhar, em tempo quase real, o endpoint:

```http
POST http://apioci.argus.app.br:23243/apiargus/report/ligacoesdetalhadas
```

O frontend consulta o backend local a cada 5 segundos e plota o total de ligações retornadas na janela configurada.

## Configuração

Crie o arquivo `.env` a partir do exemplo:

```powershell
Copy-Item .env.example .env
```

Preencha:

```env
ARGUS_TOKEN_SIGNATURE=seu_token
ARGUS_BASE_URL=http://apioci.argus.app.br:23243/apiargus
ARGUS_ID_CAMPANHA=123
ARGUS_CAMPANHA_NOME=Vieiracred
ARGUS_ATTENDANCE_WEBHOOK_URL=https://app.apivieiracred.com.br/webhook/api/argus-ligacoes
ARGUS_ID_GRUPO_USUARIO=267
ARGUS_ULTIMOS_MINUTOS=5
```

## Rodar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://127.0.0.1:5055
```

## Payload enviado

```json
{
  "idCampanha": 123,
  "idGrupoUsuario": 267,
  "ultimosMinutos": 5
}
```

Campos opcionais aceitos por `.env`:

- `ARGUS_ID_LOTE`
- `ARGUS_ID_USUARIO`
- `ARGUS_ID_STATUS_LIGACAO`
- `ARGUS_ID_TABULACAO`
- `ARGUS_CAMPANHA_NOME`
- `ARGUS_ATTENDANCE_WEBHOOK_URL`
