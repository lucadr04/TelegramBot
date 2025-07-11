import os
from dotenv import load_dotenv
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from browseapi import BrowseAPI
from math import log10
import asyncio

# Informazioni aggiuntive ed elimino quelle ridondanti
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

# .env 
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
APP_ID = os.getenv("APP_ID")
CERT_ID = os.getenv("CERT_ID")
USER_TOKEN = os.getenv("USER_TOKEN")

### SEZIONE DI INIZIALIZZAZIONE DEL BOT

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:      
    context.user_data["data"] = {}
    context.user_data["current"] = 0
    
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
        [InlineKeyboardButton("Prezzo totale minore", callback_data=str("set_sorting_MinTotPrice"))],
        [
            InlineKeyboardButton("Prezzo minore", callback_data=str("set_sorting_MinPrice")),
            InlineKeyboardButton("Shipping minore", callback_data=str("set_sorting_MinShip"))
        ],
        [InlineKeyboardButton("Dealer migliore", callback_data=str("set_sorting_BestDealer"))],
        [InlineKeyboardButton("Condizioni migliori", callback_data=str("set_sorting_BestConditions"))],
        [InlineKeyboardButton("Grading sperimentale", callback_data=str("set_sorting_MyGrading"))],
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

### SEZIONE DI RICERCA ED ORDINAMENTO ARTICOLI

# Funzione che chiama l'API per richiedere articoli al server tramite Browsing API
async def browse_ebay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Se l'utente non ha configurato la sua ricerca, questi sono i dati di default 
    if "location" not in context.user_data: context.user_data["location"] = "IT"                
    if "sorting" not in context.user_data: context.user_data["sorting"] = "MyGrading"      
    keyword = update.message.text
    
    api = BrowseAPI(APP_ID, CERT_ID)

    context.user_data["placeholder"] = await context.bot.send_photo(
        chat_id=update.message.chat_id,
        caption=f"Ricerca avviata per: {keyword}",
        parse_mode="Markdown",
        photo="https://www.pngall.com/wp-content/uploads/13/eBay-Logo-PNG-Image.png"
    )

    # L'API utilizza chiamate HTTP bloccanti. Il bot di Telegram è asincrono
    # Telegram non aspetta la fine della chiamata e procede dritto
    # Bisogna usare un exploit per non bloccare il loop principale
    # Questa funzioncina è un workaround
    # Crea essenzialmente un thread e attende fino al completamento
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        # Documentation https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
        None, lambda: api.execute('search', [{
            'q': keyword, 'limit': 50, 'filter': f"itemLocationCountry:{context.user_data['location']}"}])
    )
    
    try:
        raw_data = response[0].itemSummaries
    except (AttributeError, IndexError):
        await update.message.reply_text("Nessun risultato trovato per la ricerca.")
        return

    data = extractor(raw_data)    # Estraggo dalla response solo il necessario

    data = sort_by_attribute(data, context)
    context.user_data["data"] = data
    context.user_data["current"] = 0

    await show_item(context)

# Funzione che estrae i dati utili dalla response dell'API
def extractor(raw_data):
    extracted = []

    for item in raw_data:
        # Alcuni campi non ci sono sempre
        try:
            shipping_price = item.shippingOptions[0].shippingCost.value
        except (AttributeError, IndexError):
            shipping_price = 0

        try:
            conditionScore = int(item.conditionId)
        except (ValueError, TypeError, AttributeError):
            conditionScore = 1

        price = int(float(item.price.value))
        shipping = int(float(shipping_price))
        total = price + shipping
        fP = int(float(item.seller.feedbackPercentage))
        fS = int(item.seller.feedbackScore)
        feedback = fP * log10(fS + 1)
        myGrade = int(feedback + (1 / price) * 1000 + (100000 / conditionScore))

        extracted.append({
            "title": item.title,
            "url": item.itemWebUrl,
            "image": item.image.imageUrl,
            "price": price,
            "shipping": shipping,
            "currency": item.price.currency,
            "condition": item.condition,
            "feedbackP": fP,
            "feedbackS": fS,
            "total": total,
            "feedback": feedback,
            "conditionScore": conditionScore,
            "myGrade": myGrade
        })
    return extracted

def sort_by_attribute(data, context):
    sort = context.user_data["sorting"]
    sort_map = {
        "MinTotPrice":   ("total", False),
        "MinPrice":      ("price", False),
        "MinShip":       ("shipping", False),
        "BestDealer":    ("feedback", True),
        "BestConditions":("conditionScore", False),
        "MyGrading":     ("myGrade", True),
    }

    key_name, reverse = sort_map[sort]
    return sorted(data, key=lambda x: x[key_name], reverse=reverse)

# Funzione che mostra l'articolo con index current
async def show_item(context):
    idx = context.user_data["current"]
    data = context.user_data["data"]
    item = data[idx]
    text = (f"**[{item['title']}**]({item['url']})**\n\n"
    f"Prezzo: {item['total']}{item['currency']} ({item['price']}+{item['shipping']})\n"
    f"Condizioni: {item['condition']}\n"
    f"Score venditore: {item['feedbackP']}% ({item['feedbackS']})\n")

    keyboard = []
    if idx > 0:
        keyboard.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev"))
    if idx < len(data) - 1:
        keyboard.append(InlineKeyboardButton("Next ➡️", callback_data="next"))

    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

    # Edit media: photo + caption + buttons
    media = InputMediaPhoto(media=item['image'], caption=text, parse_mode="Markdown")
    await context.user_data["placeholder"].edit_media(media=media, reply_markup=reply_markup)

### MAIN

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
    else:
        if query.data == "prev":
            context.user_data["current"] -= 1
        elif query.data == "next":
            context.user_data["current"] += 1
        await show_item(context)

def main() -> None:
    """Bot Start"""
    # Creo l'applicazione
    application = Application.builder().token(BOT_TOKEN).build()

    # Definisco i comandi
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setup", setup))
    application.add_handler(CommandHandler("show", show))

    # Ricerca della keyword inviata
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, browse_ebay))

    # Dichiaro l'handler
    application.add_handler(CallbackQueryHandler(callback_manager))
    
    # Comando che dice al bot di continuare ad essere eseguito fino a "CtrlC"
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()