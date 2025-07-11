# A quanto pare, dopo ORE di ricerca, ho scoperto che Finding API è stata deprecata :(
# Qualche mese fa letteralmente, per questo in giro non ho trovato info utilli
# Quindi devo usarne un'altra
 
import os
from dotenv import load_dotenv
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import requests
import json

# Informazioni aggiuntive ed elimino quelle ridondanti
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

# .env 
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EBAY_TOKEN = os.getenv("APP_ID")
USER_TOKEN = os.getenv("USER_TOKEN")

### SEZIONE DI INIZIALIZZAZIONE DEL BOT

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Dati necessari alla ricerca ed al sorting
    if "location" not in context.user_data:
        context.user_data["location"] = "IT"                # che amazon cercare?
    if "sorting" not in context.user_data:
        context.user_data["sorting"] = "lowest_price"       # Per le modalità guardare sotto
    
    
    # Messaggio introduttivo
    await update.message.reply_text(
        "Ciao! Sono un bot per cercare offerte su Ebay.\n"
        "Usa /setup per modificare le impostazioni di ricerca\n"
        "Usa /show per mostrare le impostazioni selezionate\n"
        "Poi scrivimi un prodotto per iniziare!"
    )

# Mostra le opzioni
async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    location = context.user_data.get("location")
    sorting = context.user_data.get("sorting")

    msg = (
        f"Impostazioni attuali:\n"
        f"Posizione: `{location}`\n"
        f"Ordinamento: `{sorting}`\n"
    )
    await update.message.reply_text(msg)

# Seleziono l'opzione da modificare
async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Impostazioni. Il callback manager reindirizzerà all'handler scelto
    keyboard = [
        [InlineKeyboardButton("Ordinamento", callback_data=str("handler_sorting"))],
        [InlineKeyboardButton("Specifica zona", callback_data=str("handler_location"))],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Quale impostazione vuoi modificare?", 
                                    reply_markup=reply_markup)

# Seleziono il sorting
async def sorting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Prezzo minore", callback_data=str("set_sorting_MinPrice"))],
        [InlineKeyboardButton("Dealer migliore", callback_data=str("set_sorting_BestDealer"))],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Scegli il tipo di sorting", 
                                                   reply_markup=reply_markup)

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Italia IT", callback_data=str("set_location_IT"))],
        [InlineKeyboardButton("Germania DE", callback_data=str("set_location_DE"))],
        [InlineKeyboardButton("Spagna ES", callback_data=str("set_location_ES"))],
        [InlineKeyboardButton("Inghilterra GB", callback_data=str("set_location_GB"))],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Scegli il tipo di sorting", 
                                                   reply_markup=reply_markup)

# Dizionario per gestire i callback
callback_map = {
    'handler_sorting': sorting,
    'handler_location': location
}

# Gestore dei callback
async def callback_manager(update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("handler_"):
        # Recupera la funzione corrispondente al callback_data
        handler = callback_map.get(query.data)
        await handler(update, context)
    elif query.data.startswith("set_"):
        # Imposto la variabile (sfrutto la stringa callback_data)
        param = query.data.split("_")[1]
        new = query.data.split("_")[2]
        context.user_data[param] = new 
        await update.callback_query.edit_message_text(f"Modifica eseguita! ({param}:{new})")

### SEZIONE DI RICERCA ED ORDINAMENTO ARTICOLI

async def search_ebay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text     
    location = context.user_data.get("location", "IT")
    sorting = context.user_data.get("sorting", "lowest_price")

    headers = {
        "X-EBAY-SOA-OPERATION-NAME": "findItemsByKeywords",
        "X-EBAY-SOA-SERVICE-VERSION": "1.13.0",
        "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
        "X-EBAY-SOA-RESPONSE-DATA-FORMAT": "JSON",
        "X-EBAY-SOA-SECURITY-APPNAME": EBAY_TOKEN,
    }

    payload = {
        "keywords": keyword,
        "paginationInput": {
            "entriesPerPage": 5,
            "pageNumber": 1
        },
        "sortOrder": "PricePlusShippingLowest" if sorting == "lowest_price" else "BestMatch"
    }

    try:
        response = requests.post(
            "https://svcs.ebay.com/services/search/FindingService/v1",
            headers=headers,
            json={"findItemsByKeywordsRequest": payload}
        )

        try:
            data = response.json()
            logging.info("Full eBay response:\n%s", json.dumps(data, indent=2))

            if "findItemsByKeywordsResponse" not in data:
                await update.message.reply_text("Errore: risposta eBay inattesa. Controlla i log.")
                return

            items = data["findItemsByKeywordsResponse"][0]["searchResult"][0].get("item", [])
        except Exception as e:
            logging.exception("Errore analizzando la risposta eBay:")
            await update.message.reply_text(f"Errore leggendo la risposta da eBay: {e}")
            return
        
        if not items:
            await update.message.reply_text("Nessun risultato trovato.")
            return

        # Show results
        for item in items[:3]:  # show top 3 items
            title = item["title"][0]
            price = item["sellingStatus"][0]["currentPrice"][0]["__value__"]
            url = item["viewItemURL"][0]

            msg = f"*{title}*\n💸 Prezzo: €{price}\n🔗 [Link]({url})"
            await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Errore nella richiesta a eBay: {e}")
        await update.message.reply_text("Errore nella richiesta a eBay.")

# Elimino dagli oggetti ciò che non mi serve
def extract_items(raw_items):
    extracted = []
    for item in raw_items:
        try:
            extracted.append({
                "title": item.title,
                "price": float(item.sellingStatus.currentPrice.value),
                "url": item.viewItemURL

            })
        except AttributeError:
            continue  # skip if missing data
    return extracted

# Funzione di debug per vedere il JSON ottenuto (grazie gpt)
def salva_risposta_ebay(response, nome_file="ebay_response.json"):
    try:
        with open(nome_file, "w", encoding="utf-8") as f:
            # Usa dict() per convertire la risposta eBay in formato standard Python
            json.dump(response.dict(), f, indent=2, ensure_ascii=False)
        print(f"Risposta salvata in {nome_file}")
    except Exception as e:
        print(f"Errore durante il salvataggio: {e}")

### MAIN

def main() -> None:
    """Bot Start"""
    # Creo l'applicazione
    application = Application.builder().token(BOT_TOKEN).build()

    # Definisco i comandi
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setup", setup))
    application.add_handler(CommandHandler("show", show))

    # Ricerca della keyword inviata
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_ebay))

    # Dichiaro l'handler
    application.add_handler(CallbackQueryHandler(callback_manager))
    
    # Comando che dice al bot di continuare ad essere eseguito fino a "CtrlC"
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()