# -*- coding: utf-8 -*-
"""NadinBuh Bot — Бухгалтер Надежда"""

import os
import logging
from pathlib import Path
from urllib.parse import quote
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN    = os.environ.get("BOT_TOKEN", "8696501429:AAEq8Vs0OfPP0nfzSc2jUmErQBwvGonmEjE")
TG_NICK  = "Nadezhda_Gizh"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DB_URL   = os.environ.get("DATABASE_URL", "")

GUIDE_IP     = Path("files/Гайд_Доходы_Расходы_ИП_2026.docx")
TEMPLATE_IP  = Path("files/Шаблон_Доходы_Расходы_ИП_2026.xlsx")
GUIDE_OOO    = Path("files/Гайд_ООО_2026.docx")
TEMPLATE_OOO = Path("files/Шаблон_ООО_2026.xlsx")
GUIDE_SAMO   = Path("files/Гайд_Самозанятые_2026.docx")
GUIDE_3NDFL  = Path("files/Гайд_3НДФЛ_2026.docx")
WB_FIZ       = Path("files/Тетрадь_Справки_и_декларация.docx")
WB_IP        = Path("files/Тетрадь_Налоговые_вычеты.docx")
WB_SAMO      = Path("files/Тетрадь_Самозанятый_или_ИП.docx")

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── База данных ───────────────────────────────────────────────────────────────

def get_db():
    import psycopg2
    return psycopg2.connect(DB_URL)

def init_db():
    if not DB_URL:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id BIGINT PRIMARY KEY,
                        username    TEXT,
                        first_name  TEXT,
                        referred_by BIGINT,
                        joined_at   TIMESTAMP DEFAULT NOW()
                    )
                """)
            conn.commit()
        log.info("DB ready")
    except Exception as e:
        log.error(f"DB init error: {e}")

def save_user(telegram_id: int, username: str, first_name: str, referred_by: int | None = None):
    if not DB_URL:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (telegram_id, username, first_name, referred_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (telegram_id) DO NOTHING
                """, (telegram_id, username, first_name, referred_by))
            conn.commit()
    except Exception as e:
        log.error(f"save_user error: {e}")

def get_all_user_ids() -> list[int]:
    if not DB_URL:
        return []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT telegram_id FROM users")
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        log.error(f"get_all_user_ids error: {e}")
        return []

def get_stats() -> tuple[int, int, int]:
    if not DB_URL:
        return 0, 0, 0
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users WHERE joined_at > NOW() - INTERVAL '7 days'")
                week = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users WHERE joined_at > NOW() - INTERVAL '1 day'")
                today = cur.fetchone()[0]
                return total, week, today
    except Exception as e:
        log.error(f"get_stats error: {e}")
        return 0, 0, 0

def get_referral_count(telegram_id: int) -> int:
    if not DB_URL:
        return 0
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users WHERE referred_by = %s", (telegram_id,))
                return cur.fetchone()[0]
    except Exception as e:
        log.error(f"get_referral_count error: {e}")
        return 0


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def consult_btn(label: str, context_text: str) -> InlineKeyboardButton:
    msg = f"Добрый день, я хотел бы обратиться к вам за консультацией. У меня {context_text}. У меня вопрос: ..."
    return InlineKeyboardButton(label, url=f"https://t.me/{TG_NICK}?text={quote(msg)}")


MAIN_KB = ReplyKeyboardMarkup([
    ["🏢 ООО",         "💼 ИП"],
    ["🧑‍💻 Самозанятый", "👤 Физ лица"],
    ["📞 Консультация", "💸 Отблагодарить"],
    ["⭐ Отзывы",      "🔗 Моя реф. ссылка"],
], resize_keyboard=True, input_field_placeholder="Выберите раздел 👇")


def kb_ooo():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📗 УСН «Доходы»",         callback_data="ooo_usn_d")],
        [InlineKeyboardButton("📘 УСН «Доходы−Расходы»", callback_data="ooo_usn_dr")],
        [InlineKeyboardButton("👥 Найм сотрудников",     callback_data="ooo_hire")],
        [consult_btn("💬 Консультация по ООО", "ООО")],
    ])

def kb_ip():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📗 УСН «Доходы»",         callback_data="ip_usn_d")],
        [InlineKeyboardButton("📘 УСН «Доходы−Расходы»", callback_data="ip_usn_dr")],
        [InlineKeyboardButton("👥 Найм сотрудников",     callback_data="ip_hire")],
        [InlineKeyboardButton("💰 Фиксированные взносы", callback_data="ip_vznosy")],
        [InlineKeyboardButton("📓 Рабочая тетрадь — налоговые вычеты ИП", callback_data="dl_wb_ip")],
        [consult_btn("💬 Консультация по ИП", "ИП")],
    ])

def kb_samo():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Что такое самозанятость",  callback_data="samo_info")],
        [InlineKeyboardButton("🧾 Чеки и документы",         callback_data="samo_docs")],
        [InlineKeyboardButton("📄 Скачать гайд",             callback_data="samo_guide")],
        [InlineKeyboardButton("📓 Как перейти к ИП",         callback_data="dl_wb_samo")],
        [consult_btn("💬 Консультация", "самозанятый")],
    ])

def kb_fiz():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Налоги физических лиц",       callback_data="fiz_info")],
        [InlineKeyboardButton("📝 3-НДФЛ — подать декларацию",  callback_data="fiz_3ndfl")],
        [InlineKeyboardButton("📓 Рабочая тетрадь — 3-НДФЛ",   callback_data="dl_wb_fiz")],
        [consult_btn("💬 Консультация", "физическое лицо")],
    ])

def kb_files_ooo():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Гайд ООО",   callback_data="dl_guide_ooo"),
        InlineKeyboardButton("📊 Шаблон ООО", callback_data="dl_tmpl_ooo"),
    ]])

def kb_files_ip():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Гайд ИП",   callback_data="dl_guide_ip"),
        InlineKeyboardButton("📊 Шаблон ИП", callback_data="dl_tmpl_ip"),
    ]])

def kb_back_samo():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Скачать гайд для самозанятых", callback_data="samo_guide"),
    ]])

def kb_back_3ndfl():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Скачать гайд 3-НДФЛ", callback_data="dl_guide_3ndfl"),
    ]])


# ── Тексты ────────────────────────────────────────────────────────────────────

T = {

"ooo_usn_d": (
    "🏢📗 <b>ООО — УСН «Доходы»</b>\n\n"
    "<b>Ставка:</b> 6% (регионы могут снижать)\n"
    "СПб — 6%, ЛО — 6%\n\n"
    "<b>Лимиты 2026:</b>\n"
    "• Доход — до 450 млн ₽\n"
    "• Сотрудников — до 130 чел.\n\n"
    "<b>Налог можно уменьшить</b> на уплаченные страховые взносы (до 50%)\n\n"
    "<b>Особенности ООО:</b>\n"
    "• Нет фиксированных взносов «за себя» (в отличие от ИП)\n"
    "• Директор <b>обязан</b> получать зарплату (минимум МРОТ)\n"
    "• МРОТ 2026 = 22 440 руб./мес.\n"
    "• С зарплаты директора: НДФЛ 13% + взносы 30%\n\n"
    "<b>Вывод прибыли:</b> только через дивиденды или зарплату\n"
    "Дивиденды — НДФЛ 13%, не чаще 1 раза в квартал\n\n"
    "<b>Подходит когда:</b> расходы < 60% дохода, высокая маржа"
),

"ooo_usn_dr": (
    "🏢📘 <b>ООО — УСН «Доходы−Расходы»</b>\n\n"
    "<b>Ставка:</b> 15% с разницы доходы минус расходы\n"
    "СПб — 7%, ЛО — 5%\n\n"
    "<b>Минимальный налог:</b> 1% от дохода (даже при убытке)\n\n"
    "<b>🆕 С 2026 — список расходов открытый</b>\n"
    "Можно учесть любые экономически обоснованные расходы, "
    "кроме прямо запрещённых ст.270 НК РФ\n\n"
    "<b>Лимиты:</b> 450 млн ₽ / 130 сотрудников\n\n"
    "<b>Зарплата директора:</b> обязательна, учитывается как расход\n\n"
    "<b>Подходит когда:</b> расходы > 60% дохода, торговля, производство"
),

"ooo_hire": (
    "🏢👥 <b>ООО — Найм сотрудников</b>\n\n"
    "<b>Документы при оформлении:</b>\n"
    "• Трудовой договор\n"
    "• Приказ о приёме (форма Т-1)\n"
    "• Личная карточка (форма Т-2)\n"
    "• Трудовая книжка или СТД-Р\n"
    "• Копии: паспорт, СНИЛС, ИНН, диплом\n\n"
    "<b>Налоги с зарплаты:</b>\n"
    "• НДФЛ: 13% (свыше 5 млн/год — 15%)\n"
    "• Страховые взносы: 30% + от 0,2% НСиПЗ\n\n"
    "<b>🎩 Директор — обязательно:</b>\n"
    "• Минимум МРОТ = 22 440 руб./мес.\n"
    "• Без зарплаты директора — нарушение ТК РФ\n"
    "• Взносы с минималки ≈ 6 900 руб./мес.\n\n"
    "<b>Сроки выплат:</b>\n"
    "• Аванс — до 30-го текущего месяца\n"
    "• Зарплата — до 15-го следующего месяца\n\n"
    "<b>Отчётность по сотрудникам:</b> РСВ и ЕФС-1 ежеквартально"
),

"ip_usn_d": (
    "💼📗 <b>ИП — УСН «Доходы»</b>\n\n"
    "<b>Ставка:</b> 6% (регионы могут снижать до 1%)\n"
    "СПб — 6%, ЛО — 6%\n\n"
    "<b>Лимиты 2026:</b>\n"
    "• Доход — до 450 млн ₽\n"
    "• Сотрудников — до 130 чел.\n\n"
    "<b>Уменьшение налога на взносы:</b>\n"
    "• Без сотрудников — до 100% налога\n"
    "• С сотрудниками — до 50%\n\n"
    "<b>Фикс. взносы 2026:</b> 57 390 руб.\n"
    "+ 1% с дохода свыше 300 тыс. ₽\n\n"
    "<b>Подходит когда:</b> расходы < 60% дохода, услуги, консалтинг"
),

"ip_usn_dr": (
    "💼📘 <b>ИП — УСН «Доходы−Расходы»</b>\n\n"
    "<b>Ставка:</b> 15% с разницы\n"
    "СПб — 7%, ЛО — 5%\n\n"
    "<b>Минимальный налог:</b> 1% от дохода\n\n"
    "<b>🆕 С 2026 — список расходов открытый</b>\n"
    "пп.45 п.1 ст.346.16 НК РФ — любые обоснованные расходы,\n"
    "кроме запрещённых ст.270 НК РФ\n\n"
    "<b>Фикс. взносы:</b> 57 390 руб. включаются в расходы\n\n"
    "<b>Подходит когда:</b> расходы > 60% дохода, торговля, производство"
),

"ip_hire": (
    "💼👥 <b>ИП — Найм сотрудников</b>\n\n"
    "<b>Документы при оформлении:</b>\n"
    "• Трудовой договор\n"
    "• Приказ о приёме\n"
    "• Трудовая книжка / СТД-Р\n"
    "• Копии: паспорт, СНИЛС, ИНН\n\n"
    "<b>Налоги с зарплаты:</b>\n"
    "• НДФЛ: 13% (свыше 5 млн/год — 15%)\n"
    "• Страховые взносы: 30% + от 0,2% НСиПЗ\n\n"
    "<b>Сроки выплат:</b>\n"
    "• Аванс — до 30-го текущего месяца\n"
    "• Зарплата — до 15-го следующего месяца\n\n"
    "<b>Отчётность:</b> РСВ и ЕФС-1 ежеквартально, 6-НДФЛ\n\n"
    "<i>У ИП нет обязанности платить себе зарплату — "
    "деньги можно брать из оборота в любое время</i>"
),

"ip_vznosy": (
    "💼💰 <b>ИП — Фиксированные страховые взносы 2026</b>\n\n"
    "<b>Фиксированная часть:</b> 57 390 руб.\n"
    "Срок уплаты: до 31 декабря 2026\n\n"
    "<b>Дополнительный взнос:</b> 1% с дохода свыше 300 000 руб.\n"
    "Срок уплаты: до 1 июля 2027\n\n"
    "<b>Максимум в 2026:</b> 379 208 руб.\n\n"
    "<b>Уплата через ЕНП</b> — единый налоговый платёж на счёт\n\n"
    "<b>Как уменьшить налог УСН «Доходы»:</b>\n"
    "• Без сотрудников — взносы вычитаются из налога полностью\n"
    "• С сотрудниками — до 50% налога\n"
    "• Можно платить взносы поквартально и сразу уменьшать авансы\n\n"
    "<b>При нулевом доходе</b> взносы всё равно платятся.\n"
    "Исключения: декрет, уход за ребёнком до 1.5 лет, служба в армии"
),

"samo_info": (
    "🧑‍💻 <b>Самозанятость (НПД) — 2026</b>\n\n"
    "<b>Ставки:</b>\n"
    "• 4% — оплата от физических лиц\n"
    "• 6% — оплата от ИП и юрлиц\n\n"
    "<b>Лимит дохода:</b> 2,4 млн ₽ в год\n\n"
    "<b>Как открыть — 3 шага:</b>\n"
    "1. Скачать приложение «Мой налог»\n"
    "2. Зарегистрироваться через Госуслуги или по паспорту\n"
    "3. Всё — можно работать и пробивать чеки\n\n"
    "<b>Нельзя:</b>\n"
    "• Нанимать сотрудников\n"
    "• Перепродавать чужие товары\n"
    "• Работать по агентским договорам\n"
    "• Совмещать с УСН или ОСН\n\n"
    "<b>Налоговый бонус при регистрации:</b> 10 000 руб.\n"
    "Ставки временно: 3% (физлица) / 4% (юрлица) — пока не исчерпан бонус\n\n"
    "<b>Взносы:</b> не обязательны (но можно добровольно в ПФР)\n"
    "<b>Отчётность:</b> нет — всё автоматически через «Мой налог»"
),

"samo_docs": (
    "🧑‍💻🧾 <b>Самозанятый — Чеки и документы</b>\n\n"
    "<b>Как пробить чек в «Мой налог»:</b>\n"
    "Новая продажа → сумма → кто платит → наименование → «Выдать чек»\n\n"
    "<b>Когда выдавать чек:</b>\n"
    "• Наличные / перевод от физлица — <b>сразу</b>\n"
    "• Безнал от юрлица — <b>не позднее 9-го числа</b> следующего месяца\n\n"
    "<b>Работа с физическими лицами:</b>\n"
    "• Договор — не обязателен\n"
    "• Чек — единственный обязательный документ\n\n"
    "<b>Работа с юридическими лицами и ИП:</b>\n"
    "• Договор — <b>обязателен</b>\n"
    "• Акт выполненных работ — <b>обязателен</b>\n"
    "• Чек из «Мой налог» — <b>обязателен</b>\n\n"
    "<b>Итого — что отдавать клиенту:</b>\n"
    "👤 Физлицо: чек\n"
    "💼 ИП: договор + чек\n"
    "🏢 ООО: договор + акт + чек"
),

"fiz_info": (
    "👤 <b>Физические лица — налоги</b>\n\n"
    "<b>НДФЛ — ставки 2026:</b>\n"
    "• 13% — доход до 2,4 млн ₽ в год\n"
    "• 15% — от 2,4 до 5 млн ₽\n"
    "• 18% — от 5 до 20 млн ₽\n"
    "• 20% — от 20 до 50 млн ₽\n"
    "• 22% — свыше 50 млн ₽\n\n"
    "<b>Что облагается НДФЛ:</b>\n"
    "• Зарплата\n"
    "• Продажа имущества (квартира, машина, дача)\n"
    "• Сдача жилья в аренду\n"
    "• Выигрыши, призы\n\n"
    "<b>Налоговые вычеты — можно вернуть налог:</b>\n"
    "• Имущественный — при покупке жилья (до 260 000 руб.)\n"
    "• Социальный — лечение, обучение (до 19 500 руб./год)\n"
    "• Стандартный — на детей (1 400−6 000 руб./мес.)\n"
    "• Инвестиционный — по ИИС"
),

"fiz_3ndfl": (
    "👤📝 <b>3-НДФЛ — декларация</b>\n\n"
    "<b>Кто обязан подать:</b>\n"
    "• Продал квартиру/машину раньше минимального срока владения\n"
    "• Сдаёт жильё в аренду\n"
    "• Получил доход из-за рубежа\n\n"
    "<b>Кто подаёт добровольно</b> (для вычета):\n"
    "• Купил жильё → имущественный вычет\n"
    "• Платил за лечение/обучение → социальный вычет\n"
    "• Открыл ИИС → инвестиционный вычет\n\n"
    "<b>Сроки:</b>\n"
    "• Подача (обязательная): до <b>30 апреля</b> за прошлый год\n"
    "• Уплата налога: до <b>15 июля</b>\n"
    "• Для вычета — в любое время\n\n"
    "<b>Штраф</b> за просрочку: 5% в месяц, минимум 1 000 руб.\n\n"
    "📄 Скачайте пошаговый гайд по подаче 3-НДФЛ 👇"
),

}


# ── Хендлеры ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None

    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referred_by = int(arg[4:])
                if referred_by == user.id:
                    referred_by = None
            except ValueError:
                pass

    save_user(user.id, user.username, user.first_name, referred_by)

    await update.message.reply_text(
        "👋 Привет! Я помощник <b>Надежды Гижинской</b> — бухгалтера для предпринимателей.\n\n"
        "Выберите нужный раздел 👇",
        parse_mode="HTML",
        reply_markup=MAIN_KB,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total, week, today = get_stats()
    await update.message.reply_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total}</b>\n"
        f"📅 За последние 7 дней: <b>{week}</b>\n"
        f"🔆 Сегодня: <b>{today}</b>",
        parse_mode="HTML",
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    user = update.effective_user

    if txt == "🏢 ООО":
        await update.message.reply_text("🏢 <b>ООО</b> — выберите тему:",
            parse_mode="HTML", reply_markup=kb_ooo())

    elif txt == "💼 ИП":
        await update.message.reply_text("💼 <b>ИП</b> — выберите тему:",
            parse_mode="HTML", reply_markup=kb_ip())

    elif txt == "🧑‍💻 Самозанятый":
        await update.message.reply_text("🧑‍💻 <b>Самозанятый</b> — выберите тему:",
            parse_mode="HTML", reply_markup=kb_samo())

    elif txt == "👤 Физ лица":
        await update.message.reply_text("👤 <b>Физические лица</b> — выберите тему:",
            parse_mode="HTML", reply_markup=kb_fiz())

    elif txt == "📞 Консультация":
        msg = "Добрый день, я хотел бы обратиться к вам за консультацией. У меня вопрос: ..."
        url = f"https://t.me/{TG_NICK}?text={quote(msg)}"
        await update.message.reply_text(
            "📞 <b>Консультация с бухгалтером</b>\n\n"
            "Надежда Гижинская — бухгалтер для предпринимателей\n\n"
            "💬 @Nadezhda_Gizh\n"
            "📱 +7 (921) 593-51-16\n"
            "📧 gizhinskayanadysha@gmail.com",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Написать в Telegram", url=url)
            ]])
        )

    elif txt == "💸 Отблагодарить":
        await update.message.reply_text(
            "💸 <b>Отблагодарить</b>\n\n"
            "Если материалы оказались полезными — буду рада 🙏\n\n"
            "Перевод по номеру телефона:\n"
            "📱 <b>+7 (921) 593-51-16</b>\n"
            "🏦 Тинькофф (СБП)\n\n"
            "Или оставьте отзыв — это тоже очень ценно!\n"
            "Каждое слово поддержки помогает расти 🌱",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Написать отзыв", url="https://t.me/FeedbackNadinBuh"),
            ]]),
        )

    elif txt == "⭐ Отзывы":
        await update.message.reply_text(
            "⭐ <b>Отзывы</b>\n\n"
            "Уже пользовались материалами или были на консультации?\n\n"
            "Поделитесь своим опытом — это помогает другим предпринимателям "
            "найти надёжного бухгалтера и принять правильное решение 🙏\n\n"
            "Буду очень благодарна за ваш отзыв! 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Написать отзыв", url="https://t.me/FeedbackNadinBuh"),
            ]]),
        )

    elif txt == "🔗 Моя реф. ссылка":
        ref_link = f"https://t.me/NadinBuhAssistBot?start=ref_{user.id}"
        count = get_referral_count(user.id)
        await update.message.reply_text(
            f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
            f"Поделитесь ссылкой — и друзья получат удобный доступ к материалам по бухгалтерии:\n\n"
            f"<code>{ref_link}</code>\n\n"
            f"👥 По вашей ссылке пришли: <b>{count}</b> чел.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={quote(ref_link)}&text={quote('Полезный бот по налогам и бухгалтерии от Надежды Гижинской 👇')}")
            ]])
        )


async def handle_forward_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересланное сообщение от админа → рассылка всем пользователям."""
    msg = update.message
    if not msg or msg.chat_id != ADMIN_ID:
        return
    # Проверяем что сообщение пересланное
    if not (msg.forward_origin or msg.forward_date):
        return

    user_ids = get_all_user_ids()
    if not user_ids:
        await msg.reply_text("⚠️ База пользователей пуста.")
        return

    await msg.reply_text(f"📤 Начинаю рассылку {len(user_ids)} пользователям...")

    success, failed = 0, 0
    for uid in user_ids:
        if uid == ADMIN_ID:
            continue
        try:
            await context.bot.forward_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            success += 1
        except Exception:
            failed += 1

    await msg.reply_text(
        f"✅ Разослано: <b>{success}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>",
        parse_mode="HTML",
    )


async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data in T:
        text = T[data]
        if data.startswith("ooo_"):
            kb = kb_files_ooo()
        elif data.startswith("ip_"):
            kb = kb_files_ip()
        elif data == "samo_docs":
            kb = kb_back_samo()
        elif data == "fiz_3ndfl":
            kb = kb_back_3ndfl()
        else:
            kb = None
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    elif data == "samo_guide":
        await send_file(q.message.reply_document, GUIDE_SAMO,
            "📄 <b>Гайд для самозанятых 2026</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_guide_3ndfl":
        await send_file(q.message.reply_document, GUIDE_3NDFL,
            "📄 <b>Пошаговый гайд по подаче 3-НДФЛ</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_guide_ooo":
        await send_file(q.message.reply_document, GUIDE_OOO,
            "📄 <b>Гайд для ООО 2026</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_tmpl_ooo":
        await send_file(q.message.reply_document, TEMPLATE_OOO,
            "📊 <b>Шаблон учёта для ООО 2026</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_guide_ip":
        await send_file(q.message.reply_document, GUIDE_IP,
            "📄 <b>Гайд «Доходы и расходы ИП 2026»</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_tmpl_ip":
        await send_file(q.message.reply_document, TEMPLATE_IP,
            "📊 <b>Шаблон учёта доходов и расходов ИП 2026</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_wb_fiz":
        await send_file(q.message.reply_document, WB_FIZ,
            "📓 <b>Рабочая тетрадь — Справки и декларация (3-НДФЛ)</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_wb_ip":
        await send_file(q.message.reply_document, WB_IP,
            "📓 <b>Рабочая тетрадь — Мои налоговые вычеты</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")

    elif data == "dl_wb_samo":
        await send_file(q.message.reply_document, WB_SAMO,
            "📓 <b>Рабочая тетрадь — Мой статус: Самозанятый или ИП?</b>\n\n💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16")


async def send_file(reply_fn, path: Path, caption: str):
    if not path.exists():
        await reply_fn(
            "📎 Файл будет доступен в ближайшее время.\n"
            "Напишите напрямую — пришлю лично!\n\n"
            "💬 @Nadezhda_Gizh | 📱 +7 (921) 593-51-16"
        )
        return
    await reply_fn(document=path.open("rb"), filename=path.name,
                   caption=caption, parse_mode="HTML")


# ── Запуск ────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        handle_forward_broadcast,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(CallbackQueryHandler(cb_handler))

    port = int(os.environ.get("PORT", 8080))
    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

    if render_host:
        log.info(f"Webhook mode: https://{render_host}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TOKEN,
            webhook_url=f"https://{render_host}/{TOKEN}",
            drop_pending_updates=True,
        )
    else:
        log.info("Polling mode (local)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
