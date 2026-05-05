# -*- coding: utf-8 -*-
"""NadinBuh Bot — Бухгалтер Надежда"""

import os
import asyncio
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
GUIDE_115FZ  = Path("files/Гайд_115ФЗ_2026.docx")
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
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS leads (
                        id         SERIAL PRIMARY KEY,
                        name       TEXT,
                        phone      TEXT,
                        email      TEXT,
                        message    TEXT,
                        source     TEXT DEFAULT 'site',
                        created_at TIMESTAMP DEFAULT NOW()
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

def save_lead(name: str, phone: str, email: str, message: str, source: str = "site"):
    if not DB_URL:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO leads (name, phone, email, message, source)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name[:200], phone[:50], email[:200], message[:1000], source))
            conn.commit()
    except Exception as e:
        log.error(f"save_lead error: {e}")

def get_leads(limit: int = 20):
    if not DB_URL:
        return []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name, phone, email, message,
                           to_char(created_at, 'DD.MM.YYYY HH24:MI')
                    FROM leads ORDER BY created_at DESC LIMIT %s
                """, (limit,))
                return cur.fetchall()
    except Exception as e:
        log.error(f"get_leads error: {e}")
        return []

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

def user_exists(telegram_id: int) -> bool:
    if not DB_URL:
        return False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users WHERE telegram_id = %s", (telegram_id,))
                return cur.fetchone() is not None
    except Exception:
        return False

def get_referral_tree(telegram_id: int) -> tuple:
    if not DB_URL:
        return [], []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT first_name, username FROM users WHERE referred_by = %s ORDER BY joined_at DESC",
                    (telegram_id,)
                )
                direct = cur.fetchall()
                cur.execute("""
                    SELECT u.first_name, u.username FROM users u
                    JOIN users ref ON ref.telegram_id = u.referred_by
                    WHERE ref.referred_by = %s ORDER BY u.joined_at DESC
                """, (telegram_id,))
                indirect = cur.fetchall()
                return direct, indirect
    except Exception as e:
        log.error(f"get_referral_tree error: {e}")
        return [], []


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
        [InlineKeyboardButton("🔒 Блокировка по 115-ФЗ",        callback_data="fiz_115fz")],
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

def kb_ooo_usn_d():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Гайд ООО",   callback_data="dl_guide_ooo"),
         InlineKeyboardButton("📊 Шаблон ООО", callback_data="dl_tmpl_ooo")],
        [InlineKeyboardButton("📋 Что обязательно вести на этом режиме", callback_data="ooo_usn_d_records")],
    ])

def kb_ip_usn_d():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Гайд ИП",   callback_data="dl_guide_ip"),
         InlineKeyboardButton("📊 Шаблон ИП", callback_data="dl_tmpl_ip")],
        [InlineKeyboardButton("📋 Что обязательно вести на этом режиме", callback_data="ip_usn_d_records")],
    ])

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
    "<b>Подходит когда:</b> расходы &lt; 60% дохода, высокая маржа"
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
    "<b>Подходит когда:</b> расходы &gt; 60% дохода, торговля, производство"
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
    "<b>Подходит когда:</b> расходы &lt; 60% дохода, услуги, консалтинг"
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
    "<b>Подходит когда:</b> расходы &gt; 60% дохода, торговля, производство"
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

"ip_usn_d_records": (
    "💼📗 <b>ИП на УСН «Доходы» — что обязательно вести</b>\n\n"
    "<b>📌 Всегда обязательно:</b>\n"
    "• <b>КУДиР</b> — книга учёта доходов. Ведётся весь год, хранить 5 лет (ст. 346.24 НК РФ). "
    "Сдавать никуда не нужно, но по запросу налоговой — предоставить в распечатанном и подписанном виде\n"
    "• <b>Первичные документы</b> — договоры, акты, счета, накладные, чеки. Хранить 5 лет\n"
    "• <b>Кассовые документы</b> — если работаете с наличными: ПКО, РКО, кассовая книга\n\n"
    "<b>📅 Платежи и отчётность:</b>\n"
    "• Авансовые платежи по УСН: до 28 апреля, 28 июля, 28 октября\n"
    "• Декларация УСН — 1 раз в год, до <b>25 апреля</b>\n"
    "• Итоговый налог — до <b>28 апреля</b>\n\n"
    "<b>👥 Если есть сотрудники — дополнительно:</b>\n"
    "• РСВ — ежеквартально до 25-го числа\n"
    "• 6-НДФЛ — ежеквартально до 25-го числа\n"
    "• ЕФС-1 — ежеквартально\n"
    "• Персонифицированные сведения — ежемесячно до 25-го числа\n\n"
    "<b>📂 По запросу налоговой предоставляете:</b>\n"
    "• КУДиР (распечатанная, подписанная)\n"
    "• Первичные документы (договоры, акты, накладные)\n"
    "• Банковские выписки\n"
    "• Кассовые документы (если есть)"
),

"ooo_usn_d_records": (
    "🏢📗 <b>ООО на УСН «Доходы» — что обязательно вести</b>\n\n"
    "<b>📌 Всегда обязательно:</b>\n"
    "• <b>КУДиР</b> — книга учёта доходов, ст. 346.24 НК РФ. Хранить 5 лет\n"
    "• <b>Полный бухгалтерский учёт</b> (ФЗ-402) — в отличие от ИП, ООО обязано вести бухгалтерию в полном объёме\n"
    "• <b>Бухгалтерская отчётность</b> — баланс + отчёт о финансовых результатах, сдаётся до <b>31 марта</b> в ФНС и Росстат\n"
    "• <b>Кассовая дисциплина</b> — обязательна: кассовая книга, ПКО, РКО\n"
    "• <b>Протоколы собраний</b> учредителей и решения по дивидендам — хранить весь срок жизни ООО\n"
    "• <b>Первичные документы</b> — договоры, акты, накладные, счета. Хранить 5 лет\n\n"
    "<b>📅 Платежи и отчётность:</b>\n"
    "• Авансы по УСН: до 28 апреля, 28 июля, 28 октября\n"
    "• Декларация УСН — до <b>25 марта</b> (на месяц раньше, чем у ИП!)\n"
    "• Итоговый налог — до <b>28 марта</b>\n\n"
    "<b>👥 Если есть сотрудники — дополнительно:</b>\n"
    "• РСВ, 6-НДФЛ, ЕФС-1 — ежеквартально\n"
    "• Персонифицированные сведения — ежемесячно\n\n"
    "<b>📂 По запросу налоговой предоставляете:</b>\n"
    "• КУДиР\n"
    "• Первичные документы\n"
    "• Бухгалтерские регистры\n"
    "• Банковские выписки"
),

"fiz_115fz": (
    "🔒 <b>Блокировка счёта по 115-ФЗ</b>\n\n"
    "<b>За что блокируют чаще всего:</b>\n"
    "• Транзитные операции (пришло → сразу ушло)\n"
    "• Снятие наличных сразу после поступления\n"
    "• Дробление платежей (структурирование)\n"
    "• Непонятное назначение платежа\n"
    "• Непредоставление документов по запросу банка\n\n"
    "<b>Как избежать:</b>\n"
    "• Всегда указывайте точное назначение платежа (номер договора, дата)\n"
    "• Храните все первичные документы — договоры, акты, счета\n"
    "• Отвечайте на запросы банка в течение 2–3 дней\n"
    "• Не снимайте наличные без необходимости\n\n"
    "<b>Счёт заблокировали? Первые шаги:</b>\n"
    "1. Звоните в банк — узнайте причину и список документов\n"
    "2. Собирайте договоры, акты, выписки\n"
    "3. Пишите объяснительную о происхождении средств\n"
    "4. Нет ответа 3–5 дней → жалоба в ЦБ РФ (cbr.ru)\n\n"
    "📄 В гайде — полный разбор 10 причин блокировок, 8 правил защиты "
    "и 3 готовых шаблона ответа на запросы банка 👇"
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
    await update.message.chat.send_action("typing")
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

    # Возвращающийся пользователь — сразу в меню
    if user_exists(user.id):
        await update.message.reply_text(
            f"С возвращением, {user.first_name}! 👋\n\nВыберите нужный раздел 👇",
            parse_mode="HTML",
            reply_markup=MAIN_KB,
        )
        return

    # Новый пользователь — показываем согласие на обработку данных
    ref_param = str(referred_by) if referred_by else "0"
    await update.message.reply_text(
        f"Здравствуйте, {user.first_name}! 👋\n\n"
        "Рада видеть вас в своём пространстве.\n\n"
        "Я — <b>Надежда Гижинская</b>, бухгалтер для предпринимателей.\n"
        "Здесь вы найдёте гайды, шаблоны и ответы на налоговые вопросы — "
        "просто и по делу.\n\n"
        "──────────────────────\n"
        "📋 <b>Согласие на обработку персональных данных</b>\n\n"
        "Продолжая, вы соглашаетесь на обработку ваших данных "
        "(имя, Telegram ID, username) в соответствии с ФЗ-152.\n\n"
        "Данные используются только для работы бота и не передаются третьим лицам.\n"
        "<i>Оператор: Гижинская Надежда Николаевна</i>\n"
        "<i>Отзыв согласия: @Nadezhda_Gizh</i>\n\n"
        "📄 <a href=\"https://nadinbuh.ru/privacy.html\">Политика конфиденциальности</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Принимаю и продолжаю", callback_data=f"consent_{ref_param}")
        ]])
    )


async def consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user

    ref_part = q.data.replace("consent_", "")
    referred_by = int(ref_part) if ref_part != "0" else None

    save_user(user.id, user.username, user.first_name, referred_by)

    # Уведомить реферера о новом подключении
    if referred_by:
        try:
            await context.bot.send_message(
                chat_id=referred_by,
                text=f"🎉 По вашей ссылке только что присоединился(ась) <b>{user.first_name}</b>!",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await q.message.reply_text(
        "Добро пожаловать! Выберите нужный раздел 👇",
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


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not DB_URL:
        await update.message.reply_text("База данных не подключена.")
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, username, referred_by,
                           to_char(joined_at, 'DD.MM.YYYY HH24:MI')
                    FROM users ORDER BY joined_at DESC LIMIT 20
                """)
                rows = cur.fetchall()
        if not rows:
            await update.message.reply_text("База пуста.")
            return
        lines = ["👥 <b>Последние 20 пользователей:</b>\n"]
        for i, (name, uname, ref, dt) in enumerate(rows, 1):
            uname_str = f"@{uname}" if uname else "—"
            ref_str = f" ← реф.{ref}" if ref else ""
            lines.append(f"{i}. {name} ({uname_str}){ref_str} — {dt}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not DB_URL:
        await update.message.reply_text("База данных не подключена.")
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.telegram_id, u.first_name, u.username,
                           r.first_name, r.username,
                           to_char(u.joined_at, 'DD.MM.YYYY HH24:MI')
                    FROM users u
                    LEFT JOIN users r ON r.telegram_id = u.referred_by
                    ORDER BY u.joined_at DESC
                """)
                rows = cur.fetchall()
        if not rows:
            await update.message.reply_text("База пуста.")
            return

        import io, csv
        buf = io.StringIO()
        buf.write("﻿")  # BOM для корректного открытия в Excel
        w = csv.writer(buf, delimiter=";")
        w.writerow(["#", "Имя", "Username", "Telegram ID", "Пришёл от", "Дата входа"])
        for i, (tid, name, uname, ref_name, ref_uname, dt) in enumerate(rows, 1):
            if ref_uname:
                ref_str = f"@{ref_uname}"
            elif ref_name:
                ref_str = ref_name
            else:
                ref_str = ""
            w.writerow([i, name, f"@{uname}" if uname else "", tid, ref_str, dt])

        raw = buf.getvalue().encode("utf-8-sig")
        from datetime import date
        fname = f"users_{date.today().strftime('%Y%m%d')}.csv"
        await update.message.reply_document(
            document=io.BytesIO(raw),
            filename=fname,
            caption=f"📊 База пользователей — {len(rows)} чел.\nОткрывается в Excel (разделитель — точка с запятой).",
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    rows = get_leads(20)
    if not rows:
        await update.message.reply_text("Заявок с сайта пока нет.")
        return
    lines = [f"📋 <b>Заявки с сайта — последние {len(rows)}:</b>\n"]
    for name, phone, email, msg, dt in rows:
        lines.append(
            f"<b>{name}</b>\n"
            f"📞 {phone}  📧 {email}\n"
            f"💬 {msg or '—'}\n"
            f"🕐 {dt}\n"
        )
    text = "\n".join(lines)
    # Telegram лимит 4096 символов
    if len(text) > 4000:
        text = text[:4000] + "\n…(обрезано)"
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    user = update.effective_user

    # Незарегистрированный пользователь — направляем к /start
    if not user_exists(user.id):
        await update.message.reply_text(
            "👋 Чтобы начать, нажмите /start",
        )
        return

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
        msg = "Добрый день, Надежда! Хотела бы обратиться к вам за консультацией. У меня вопрос: ..."
        url = f"https://t.me/{TG_NICK}?text={quote(msg)}"
        await update.message.reply_text(
            "📞 <b>Консультация</b>\n\n"
            "Буду рада разобрать ваш вопрос лично.\n\n"
            "Пишите — отвечу в течение дня:\n"
            "💬 @Nadezhda_Gizh\n"
            "📱 +7 (921) 593-51-16\n"
            "📧 gizhinskayanadysha@gmail.com",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Написать мне в Telegram", url=url)
            ]])
        )

    elif txt == "💸 Отблагодарить":
        await update.message.reply_text(
            "💸 <b>Поддержать</b>\n\n"
            "Если материалы оказались вам полезными — буду искренне рада 🙏\n\n"
            "Вы можете поддержать меня переводом:\n"
            "📱 <b>+7 (921) 593-51-16</b>\n"
            "🏦 Тинькофф (СБП)\n\n"
            "А ещё очень ценен ваш отзыв — каждое слово помогает мне расти и помогать другим 🌱",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Оставить отзыв", url="https://t.me/FeedbackNadinBuh"),
            ]]),
        )

    elif txt == "⭐ Отзывы":
        await update.message.reply_text(
            "⭐ <b>Отзывы</b>\n\n"
            "Если вы уже работали со мной или воспользовались материалами — "
            "буду очень благодарна за ваш отзыв.\n\n"
            "Это помогает другим предпринимателям найти надёжного бухгалтера "
            "и принять правильное решение 🙏\n\n"
            "Жду вас здесь 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Оставить отзыв", url="https://t.me/FeedbackNadinBuh"),
            ]]),
        )

    elif txt == "🔗 Моя реф. ссылка":
        ref_link = f"https://t.me/NadinBuhAssistBot?start=ref_{user.id}"
        count = get_referral_count(user.id)
        await update.message.reply_text(
            f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
            f"Поделитесь ссылкой с коллегами и знакомыми — "
            f"пусть тоже получат удобный доступ к материалам по налогам и бухгалтерии:\n\n"
            f"<code>{ref_link}</code>\n\n"
            f"👥 По вашей ссылке пришли: <b>{count}</b> чел.\n\n"
            f"Спасибо, что рекомендуете меня! 🙏",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={quote(ref_link)}&text={quote('Бот по налогам и бухгалтерии от Надежды Гижинской — всё понятно и по делу 👇')}")],
                [InlineKeyboardButton("👥 Моя сеть рефералов", callback_data="ref_tree")],
            ])
        )

    else:
        await update.message.reply_text(
            "Используйте кнопки меню ниже 👇",
            reply_markup=MAIN_KB,
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
        if data == "ooo_usn_d":
            kb = kb_ooo_usn_d()
        elif data == "ip_usn_d":
            kb = kb_ip_usn_d()
        elif data == "ooo_usn_d_records":
            kb = None
        elif data == "ip_usn_d_records":
            kb = None
        elif data.startswith("ooo_"):
            kb = kb_files_ooo()
        elif data.startswith("ip_"):
            kb = kb_files_ip()
        elif data == "samo_docs":
            kb = kb_back_samo()
        elif data == "fiz_3ndfl":
            kb = kb_back_3ndfl()
        elif data == "fiz_115fz":
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📄 Скачать гайд по 115-ФЗ", callback_data="dl_guide_115fz")
            ]])
        else:
            kb = None
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    elif data == "samo_guide":
        await send_file(q.message.reply_document, GUIDE_SAMO,
            "📄 <b>Гайд для самозанятых 2026</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_guide_3ndfl":
        await send_file(q.message.reply_document, GUIDE_3NDFL,
            "📄 <b>Пошаговый гайд по подаче 3-НДФЛ</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_guide_ooo":
        await send_file(q.message.reply_document, GUIDE_OOO,
            "📄 <b>Гайд для ООО 2026</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_tmpl_ooo":
        await send_file(q.message.reply_document, TEMPLATE_OOO,
            "📊 <b>Шаблон учёта для ООО 2026</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_guide_ip":
        await send_file(q.message.reply_document, GUIDE_IP,
            "📄 <b>Гайд «Доходы и расходы ИП 2026»</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_tmpl_ip":
        await send_file(q.message.reply_document, TEMPLATE_IP,
            "📊 <b>Шаблон учёта доходов и расходов ИП 2026</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_wb_fiz":
        await send_file(q.message.reply_document, WB_FIZ,
            "📓 <b>Рабочая тетрадь — Справки и декларация (3-НДФЛ)</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_wb_ip":
        await send_file(q.message.reply_document, WB_IP,
            "📓 <b>Рабочая тетрадь — Мои налоговые вычеты</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_wb_samo":
        await send_file(q.message.reply_document, WB_SAMO,
            "📓 <b>Рабочая тетрадь — Мой статус: Самозанятый или ИП?</b>\n\nЕсли остались вопросы — пишите мне: 💬 @Nadezhda_Gizh")

    elif data == "dl_guide_115fz":
        await send_file(q.message.reply_document, GUIDE_115FZ,
            "📄 <b>Гайд: Блокировка счёта по 115-ФЗ</b>\n\n"
            "Внутри: 10 причин блокировок, 8 правил защиты, быстрые решения и 3 готовых шаблона ответа банку.\n\n"
            "Если счёт уже заблокировали — пишите: 💬 @Nadezhda_Gizh")

    elif data == "ref_tree":
        uid = q.from_user.id
        direct, indirect = get_referral_tree(uid)
        if not direct and not indirect:
            await q.message.reply_text("По вашей ссылке пока никто не присоединился. Поделитесь — и здесь появится ваша сеть 🙂")
            return
        lines = ["👥 <b>Ваша реферальная сеть:</b>\n"]
        if direct:
            lines.append(f"<b>Прямые подключения ({len(direct)}):</b>")
            for name, uname in direct:
                u = f" (@{uname})" if uname else ""
                lines.append(f"  • {name}{u}")
        if indirect:
            lines.append(f"\n<b>Косвенные подключения ({len(indirect)}):</b>")
            for name, uname in indirect:
                u = f" (@{uname})" if uname else ""
                lines.append(f"  • {name}{u}")
        await q.message.reply_text("\n".join(lines), parse_mode="HTML")


async def send_file(reply_fn, path: Path, caption: str):
    if not path.exists():
        await reply_fn(
            "📎 Файл скоро появится здесь.\n"
            "Пока можете написать мне напрямую — пришлю лично!\n\n"
            "💬 @Nadezhda_Gizh"
        )
        return
    await reply_fn(document=path.open("rb"), filename=path.name,
                   caption=caption, parse_mode="HTML")


# ── Запуск ────────────────────────────────────────────────────────────────────

def _build_app():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(CommandHandler("users",  cmd_users))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("leads",  cmd_leads))
    app.add_handler(CallbackQueryHandler(consent_callback, pattern="^consent_"))
    app.add_handler(MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        handle_forward_broadcast,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(CallbackQueryHandler(cb_handler))
    return app


async def _run_webhook(ptb_app, render_host: str, port: int):
    """Запускает aiohttp-сервер: Telegram webhook + /api/lead для заявок с сайта."""
    from aiohttp import web

    await ptb_app.initialize()
    await ptb_app.bot.set_webhook(
        url=f"https://{render_host}/{TOKEN}",
        drop_pending_updates=True,
    )
    await ptb_app.start()
    log.info(f"Webhook: https://{render_host}/{TOKEN}")

    async def tg_webhook(request):
        try:
            data = await request.json()
            update = Update.de_json(data, ptb_app.bot)
            await ptb_app.process_update(update)
        except Exception as exc:
            log.error(f"tg_webhook error: {exc}")
        return web.Response()

    async def lead_api(request):
        cors = {
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
        if request.method == "OPTIONS":
            return web.Response(headers=cors)
        try:
            data = await request.json()
            name    = (data.get("name",    "") or "")[:200]
            phone   = (data.get("phone",   "") or "")[:50]
            email   = (data.get("email",   "") or "")[:200]
            message = (data.get("message", "") or "")[:1000]
            save_lead(name, phone, email, message)
            if ADMIN_ID:
                await ptb_app.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🔔 <b>Новая заявка с сайта!</b>\n\n"
                        f"👤 {name}\n"
                        f"📞 {phone}\n"
                        f"📧 {email}\n"
                        f"💬 {message or '—'}"
                    ),
                    parse_mode="HTML",
                )
            return web.Response(
                text='{"ok":true}', content_type="application/json", headers=cors
            )
        except Exception as exc:
            log.error(f"lead_api error: {exc}")
            return web.Response(
                status=500, text='{"ok":false}',
                content_type="application/json", headers=cors
            )

    aio = web.Application()
    aio.router.add_post(f"/{TOKEN}", tg_webhook)
    aio.router.add_post("/api/lead", lead_api)
    aio.router.add_route("OPTIONS", "/api/lead", lead_api)

    runner = web.AppRunner(aio)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"HTTP server on port {port}")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await ptb_app.stop()
        await ptb_app.shutdown()
        await runner.cleanup()


def main():
    init_db()
    ptb_app = _build_app()

    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    port = int(os.environ.get("PORT", 8080))

    if render_host:
        log.info(f"Webhook mode on {render_host}")
        asyncio.run(_run_webhook(ptb_app, render_host, port))
    else:
        log.info("Polling mode (local)")
        ptb_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
