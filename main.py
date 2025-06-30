import os
import re
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters as Filters,
)
from pymongo import MongoClient

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")

print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
print(f"MONGO_URI: {MONGO_URI}")


client = MongoClient(MONGO_URI)
db = client["telegram_bot_db"]
collection = db["form_submissions"]

COMPANY, NAME, EMAIL, PHONE, CONFIRM, CHANGE_FIELD, UPDATE_FIELD = range(7)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Здравствуйте! Давайте заполним анкету.\nВведите название вашей компании:")
    return COMPANY


async def company(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["company"] = update.message.text.strip()
    await update.message.reply_text("Введите ваше имя:")
    return NAME


async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Введите ваш email:")
    return EMAIL


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", text):
        await update.message.reply_text("Пожалуйста, введите корректный email:")
        return EMAIL
    context.user_data["email"] = text
    await update.message.reply_text("Введите ваш номер телефона (например, +77001234567):")
    return PHONE


async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"^\+?\d{10,15}$", text):
        await update.message.reply_text("Введите корректный телефон (например, +77001234567):")
        return PHONE

    context.user_data["phone"] = text
    return await show_summary(update, context)


async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Отправить", "Поменять анкету"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        f"Проверьте анкету:\n"
        f"Компания: {context.user_data.get('company', '')}\n"
        f"Имя: {context.user_data.get('name', '')}\n"
        f"Email: {context.user_data.get('email', '')}\n"
        f"Телефон: {context.user_data.get('phone', '')}\n\n"
        "Что хотите сделать?",
        reply_markup=markup,
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()

    if text == "отправить":
        message = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"📌 Новая анкета:\n"
                f"Компания: {context.user_data['company']}\n"
                f"Имя: {context.user_data['name']}\n"
                f"Email: {context.user_data['email']}\n"
                f"Телефон: {context.user_data['phone']}"
            ),
        )
        context.user_data["admin_message_id"] = message.message_id
        collection.insert_one(context.user_data.copy())

        reply_keyboard = [["Поменять анкету"]]
        markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
        "Спасибо! Ваша анкета отправлена администратору. С вами скоро свяжутся.",
        reply_markup=markup
        )
        return CONFIRM

    elif text == "поменять анкету":
        admin_msg_id = context.user_data.get("admin_message_id")
        if admin_msg_id:
            try:
                await context.bot.delete_message(chat_id=ADMIN_CHAT_ID, message_id=admin_msg_id)
                await update.message.reply_text("Предыдущая анкета удалена у администратора.")
            except Exception as e:
                await update.message.reply_text(f"Не удалось удалить: {e}")

        reply_keyboard = [["Компания", "Имя"], ["Email", "Телефон"], ["Отменить"]]
        markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Что хотите поменять?", reply_markup=markup)
        return CHANGE_FIELD

    else:
        return await show_summary(update, context)


async def change_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()

    if text == "компания":
        context.user_data["field_to_change"] = "company"
        await update.message.reply_text("Введите новое название компании:", reply_markup=ReplyKeyboardRemove())
        return UPDATE_FIELD
    elif text == "имя":
        context.user_data["field_to_change"] = "name"
        await update.message.reply_text("Введите новое имя:", reply_markup=ReplyKeyboardRemove())
        return UPDATE_FIELD
    elif text == "email":
        context.user_data["field_to_change"] = "email"
        await update.message.reply_text("Введите новый email:", reply_markup=ReplyKeyboardRemove())
        return UPDATE_FIELD
    elif text == "телефон":
        context.user_data["field_to_change"] = "phone"
        await update.message.reply_text("Введите новый телефон:", reply_markup=ReplyKeyboardRemove())
        return UPDATE_FIELD
    elif text == "отменить":
        return await show_summary(update, context)
    else:
        await update.message.reply_text("Пожалуйста, выберите поле кнопкой!")
        return CHANGE_FIELD


async def update_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("field_to_change")
    value = update.message.text.strip()

    if field == "email" and not re.match(r"[^@]+@[^@]+\.[^@]+", value):
        await update.message.reply_text("Пожалуйста, введите корректный email:")
        return UPDATE_FIELD

    if field == "phone" and not re.match(r"^\+?\d{10,15}$", value):
        await update.message.reply_text("Введите корректный телефон (например, +77001234567):")
        return UPDATE_FIELD

    context.user_data[field] = value
    return await show_summary(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Анкета отменена.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            COMPANY: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, company)],
            NAME: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, name)],
            EMAIL: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, email)],
            PHONE: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, phone)],
            CONFIRM: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, confirm)],
            CHANGE_FIELD: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, change_field)],
            UPDATE_FIELD: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, update_field)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()
    app.idle()


if __name__ == '__main__':
    main()
