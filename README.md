# Sito raccolta firme per liberare il gatto

Prototipo Flask con:

- pagina pubblica per firmare la petizione;
- salvataggio firme in SQLite;
- area amministratore protetta da login;
- dashboard con andamento ultimi 30 giorni;
- export CSV di tutte le firme;
- pannello admin **Personalizza sito** per modificare intestazioni, testi, colori, layout e sezioni visibili;
- informativa privacy modificabile dal pannello admin.

## Avvio rapido

```bash
python -m venv .venv
source .venv/bin/activate  # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Su alcuni Mac il comando Python è `python3`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 app.py
```

Poi apri:

- sito pubblico: `http://localhost:5000`
- area admin: `http://localhost:5000/admin`

Credenziali demo, finché non modifichi `.env`:

- username: `admin`
- password: `cambia-questa-password`

## Personalizzazione dal pannello admin

Dopo il login vai su:

`http://localhost:5000/admin/personalizza`

Da lì puoi modificare:

- titolo del sito e titolo grande della homepage;
- sopratitolo, sottotitolo, luogo e obiettivo firme;
- tutti i testi del modulo firma;
- titoli e contenuti delle sezioni della homepage;
- testi della pagina privacy;
- colori principali;
- layout della homepage;
- larghezza massima, grandezza testo, bordi e arrotondamenti;
- sezioni visibili o nascoste;
- CSS personalizzato.

Le modifiche vengono salvate nel database `petition.db`, quindi restano anche se spegni e riaccendi il sito.

## Personalizzazione tecnica iniziale

Nel file `.env` modifica almeno:

```env
SECRET_KEY=sostituisci-con-una-stringa-lunga-casuale
ADMIN_USERNAME=admin
ADMIN_PASSWORD=una-password-forte
PETITION_GOAL=500
PETITION_TITLE=Liberiamo il gatto prelevato senza autorizzazione
PETITION_LOCATION=La tua città o quartiere
```

Questi valori servono come impostazioni iniziali. Dopo il primo avvio, titoli/layout/testi si modificano più comodamente da **Area admin > Personalizza sito**.

## Export firme

Dopo il login admin, clicca **Esporta CSV** oppure visita:

`/admin/export.csv`

Il file contiene: id, nome, email, città, commento, visibilità pubblica e data firma UTC.

## Note legali e privacy

Prima di pubblicare online:

1. personalizza la pagina privacy con titolare del trattamento, contatto, finalità, tempi di conservazione e diritti degli interessati;
2. raccogli solo i dati davvero necessari;
3. usa HTTPS;
4. scegli una password admin forte;
5. fai backup del file `petition.db`.

Questo progetto è una base tecnica, non una consulenza legale.
