# Fantacalcio Serie A → Notifiche Telegram

Script gratuito che controlla le partite di Serie A in corso e ti manda su Telegram
un messaggio ogni volta che c'è un gol, un assist, un cartellino, una sostituzione
o una decisione VAR. Gira automaticamente su GitHub Actions, non serve tenere
niente acceso.

## Cosa userai (tutto gratis)

- **Telegram Bot API** — per mandarti i messaggi.
- **[API-Football](https://dashboard.api-football.com/)** (piano Free, 100 richieste/giorno) — per i dati delle partite.
- **GitHub Actions** — per far girare lo script ogni 15 minuti, gratis per repository pubblici (e con minuti gratuiti anche su repo privati).

Tempo stimato di setup: 15-20 minuti, da fare una volta sola.

### Conferma: è davvero tutto gratis?

- **Telegram Bot API**: nessun costo, nessuna carta di credito, nessun limite rilevante per un uso personale come questo.
- **API-Football, piano Free**: nessuna carta di credito richiesta, 100 richieste/giorno, e include tutti gli endpoint senza eccezioni (fixtures live, eventi, statistiche) — la differenza con i piani a pagamento è solo il numero di richieste giornaliere e la profondità dello storico, non le funzionalità. Lo script è già progettato per restare sotto quota (vedi sotto).
- **GitHub Actions**: illimitato e gratis su repository **pubblici**. Su repository **privati** hai 2.000 minuti/mese gratis sul piano Free di GitHub; con la frequenza di questo workflow (ogni 15 min, ~4 giorni/settimana) si consumano stimativamente 900-1.800 minuti/mese, quindi ci si sta dentro ma senza troppo margine. **Consiglio:** crea il repository come **pubblico** — il codice non contiene alcuna informazione sensibile (token e chiave API restano nei "Secrets" di GitHub, mai nel codice), e così i minuti di Actions diventano illimitati senza nessun rischio di andare a pagamento. Se preferisci tenerlo privato va bene comunque, basta non allargare troppo l'orario/i giorni del cron senza controllare il consumo in Settings → Billing.

Nessuno di questi servizi chiede una carta di credito per il piano gratuito che usiamo: zero rischio di addebiti automatici.

---

## 1. Crea il bot Telegram

1. Su Telegram cerca **@BotFather** e avvia una chat.
2. Manda il comando `/newbot` e segui le istruzioni (ti chiede un nome e uno username che finisca in "bot").
3. BotFather ti darà un **token** tipo `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Salvalo, ti servirà tra poco.
4. Cerca il tuo bot appena creato (dallo username che hai scelto) e mandagli un qualsiasi messaggio (es. "ciao") per "attivare" la chat.

## 2. Trova il tuo chat_id

1. Nel browser vai su:
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates`
   (sostituendo `<IL_TUO_TOKEN>` con il token ricevuto da BotFather).
2. Nel JSON che appare cerca `"chat":{"id":XXXXXXXXX,...}` — quel numero è il tuo `chat_id`.
   Se il JSON è vuoto (`"result":[]`), assicurati di aver mandato prima un messaggio al bot come al punto 4 sopra, poi ricarica la pagina.

## 3. Crea la chiave API-Football

1. Vai su [dashboard.api-football.com](https://dashboard.api-football.com/register) e registrati (gratis).
2. Nella dashboard, nella sezione "My Access", scegli il piano **Free**.
3. Copia la tua **API-Key**.
4. (Facoltativo ma consigliato) Vai su [dashboard.api-football.com/soccer/ids](https://dashboard.api-football.com/soccer/ids) e cerca "Serie A" / Italia per confermare l'ID della lega. Nello script è già impostato **135**, che è quello corretto ad oggi; se dovesse risultare diverso, lo cambi con una variabile (vedi punto 5).

## 4. Crea il repository su GitHub

1. Su [github.com](https://github.com) crea un nuovo repository (può essere privato).
2. Carica dentro tutti i file di questo pacchetto, mantenendo la struttura delle cartelle:
   - `notify.py`
   - `requirements.txt`
   - `state/state.json`
   - `.github/workflows/serie-a-notify.yml`
   - questo `README.md`

   Il modo più semplice se non usi Git da riga di comando: sulla pagina del repo vuoto, usa "uploading an existing file" e trascina tutti i file (GitHub ricrea le sottocartelle da solo se trascini l'intera struttura, oppure crea prima manualmente i file dentro `.github/workflows/` e `state/` con "Add file → Create new file" scrivendo il percorso completo, es. `state/state.json`).

## 5. Configura i secrets

Nel repository, vai su **Settings → Secrets and variables → Actions → New repository secret** e crea questi tre secrets:

| Nome | Valore |
|---|---|
| `TELEGRAM_BOT_TOKEN` | il token ricevuto da BotFather |
| `TELEGRAM_CHAT_ID` | il chat_id trovato al punto 2 |
| `API_FOOTBALL_KEY` | la API-Key di API-Football |

Se all'ID lega 135 risultasse diverso al punto 3.4, aggiungi anche un secret `SERIE_A_LEAGUE_ID` con il valore corretto (lo script lo legge automaticamente; se non lo aggiungi usa 135 di default).

## 6. Attiva e testa

1. Vai sulla tab **Actions** del repository. Se richiesto, clicca per abilitare i workflow.
2. Apri il workflow **"Serie A Telegram Notifier"** e clicca **"Run workflow"** per lanciarlo manualmente subito (non serve aspettare l'orario programmato).
3. Dopo un minuto controlla i log del run: se tutto è configurato bene non vedrai errori (se in quel momento non ci sono partite live, semplicemente non arriverà nessun messaggio, è normale).
4. Da quel momento in poi lo script gira da solo ogni 15 minuti, nelle fasce orarie tipiche delle partite di Serie A (vedi sotto), e ti scrive su Telegram appena succede qualcosa in una partita di Serie A in corso.

---

## Come funziona (in breve)

- Lo script chiede a API-Football quali partite di Serie A sono live in questo momento, poi per ognuna scarica gli eventi (gol, cartellini, sostituzioni, VAR) e ti manda solo quelli che non ti ha già mandato prima. Se lo lanci più volte non ricevi messaggi doppi.
- Per "ricordarsi" cosa ha già notificato, il workflow salva un file `state/state.json` e lo ricommitta nel repository ad ogni esecuzione. Non toccarlo a mano.
- Il piano gratuito di API-Football ha un limite di 100 richieste/giorno. Lo script si autolimita a 90 per stare largo: se in una giornata con moltissime partite in contemporanea si avvicina al limite, si ferma da solo per il resto della giornata (fuso UTC) e ti manda un avviso su Telegram, invece di rischiare di sforare e farti bloccare l'account.

## Personalizzare gli orari

Il file `.github/workflows/serie-a-notify.yml` contiene questa riga:

```
cron: "*/15 10-22 * * 0,1,5,6"
```

Significa: ogni 15 minuti, tra le 10:00 e le 22:45 UTC, nei giorni domenica(0)/lunedì(1)/venerdì(5)/sabato(6) — cioè i giorni tipici di Serie A. Se un turno si gioca anche di martedì o mercoledì (recuperi), o vuoi controllare più/meno spesso, modifica questa riga (orari sempre in UTC) oppure lancia il workflow a mano da "Run workflow" quel giorno.

## Limiti da tenere a mente

- I dati arrivano da API-Football: in rarissimi casi un evento può comparire con qualche minuto di ritardo rispetto alla diretta TV.
- Il piano gratuito a volte ha un piccolo ritardo naturale sui dati live rispetto ai piani a pagamento — per un uso "per seguire il fantacalcio senza guardare il telefono ogni 5 minuti" è più che sufficiente.
- Questo script segue gli **eventi reali di gioco** (gol, assist, cartellini, sostituzioni), non i voti soggettivi di fantacalcio (quelli, per Serie A, non hanno una API gratuita ufficiale — arrivano il giorno dopo dai siti di settore).
