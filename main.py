import json, logging, os, re, tempfile
from pathlib import Path
from telegram import Update, MessageEntity
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('rdo-bot')
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
DATA_FILE = Path(os.environ.get('DATA_FILE', 'data.json'))
# Optional Telegram custom-emoji IDs. These are IDs, not t.me/addemoji URLs.
EMOJI_IDS = {
    'start': os.getenv('EMOJI_START', ''), 'registered': os.getenv('EMOJI_REGISTERED', ''),
    'turn': os.getenv('EMOJI_TURN', ''), 'list': os.getenv('EMOJI_LIST', ''),
    'stop': os.getenv('EMOJI_STOP', ''), 'error': os.getenv('EMOJI_ERROR', ''),
}
FALLBACK = {'start':'🎁','registered':'📝','turn':'🎉','list':'📋','stop':'🛑','error':'❌'}

def load_data():
    try:
        obj = json.loads(DATA_FILE.read_text('utf-8'))
        return obj if isinstance(obj, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        log.exception('Could not read data file; starting with empty data')
        return {}

data = load_data()

def save_data():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='rdo-', suffix='.json', dir=str(DATA_FILE.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def key(chat_id, message_id): return f'{chat_id}:{message_id}'
def is_admin_member(member): return member.status in ('administrator', 'creator')
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat: return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return is_admin_member(member)
    except Exception:
        log.exception('Admin check failed')
        return False

def reply_key(message):
    if not message or not message.reply_to_message: return None
    return key(message.chat_id, message.reply_to_message.message_id)

def custom_or_fallback(kind, text):
    eid = EMOJI_IDS.get(kind, '')
    if eid and eid.isdigit():
        prefix = FALLBACK[kind]
        return prefix + ' ' + text, [MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=0, length=len(prefix), custom_emoji_id=eid)]
    return FALLBACK[kind] + ' ' + text, None

async def send_marked(message, kind, text, reply_to_message_id=None):
    body, entities = custom_or_fallback(kind, text)
    kwargs = {'chat_id': message.chat_id, 'text': body}
    if reply_to_message_id: kwargs['reply_to_message_id'] = reply_to_message_id
    if entities: kwargs['entities'] = entities
    await message.get_bot().send_message(**kwargs)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('أهلاً! أضفني إلى القروب واجعلني مشرفاً. لبدء توزيع: ردّ على رسالتك الأصلية بكلمة توزيع.')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('للمشرفين: رد على رسالتك الأصلية بـ «توزيع»، ورد عليها بـ «قائمة» أو «وقف توزيع». لاختيار عضو اكتب رقم تسجيله كرسالة عادية. للأعضاء: ردوا على الرسالة الأصلية بالـ ID مرة واحدة.')

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type == 'private' or not msg.text: return
    text = msg.text.strip()
    low = text.casefold()

    # Starting a distribution must be a reply to the sender's own original message.
    if low == 'توزيع':
        if not await is_admin(update, context):
            await send_marked(msg, 'error', 'بدء التوزيع للمشرفين فقط')
            return
        if not msg.reply_to_message or not msg.reply_to_message.from_user or msg.reply_to_message.from_user.id != user.id:
            await send_marked(msg, 'error', 'ردّ بكلمة توزيع على رسالتك الأصلية أولاً')
            return
        k = key(chat.id, msg.reply_to_message.message_id)
        if k in data and data[k].get('active'):
            await send_marked(msg, 'error', 'هذا التوزيع مفتوح بالفعل')
            return
        data[k] = {'chat_id': chat.id, 'source_message_id': msg.reply_to_message.message_id,
                   'owner_id': user.id, 'active': True, 'registrations': [], 'user_ids': {}}
        save_data()
        await send_marked(msg, 'start', 'بدأ التسجيل! أرسل ID اللعبة بالرد على الرسالة الأصلية.', msg.reply_to_message.message_id)
        return

    # List/stop are scoped to the original message by replying to it.
    if low in ('قائمة', 'وقف توزيع'):
        if not await is_admin(update, context):
            await send_marked(msg, 'error', 'هذا الأمر للمشرفين فقط')
            return
        k = reply_key(msg)
        dist = data.get(k) if k else None
        if not dist:
            await send_marked(msg, 'error', 'رد على الرسالة الأصلية الخاصة بالتوزيع')
            return
        if low == 'قائمة':
            regs = dist['registrations']
            if not regs:
                await send_marked(msg, 'list', 'لا يوجد مسجلون حتى الآن')
            else:
                lines = [f"{r['number']}. {r['display']} — ID: {r['game_id']}" for r in regs]
                # Telegram message limit is 4096 chars.
                chunks, buf = [], 'قائمة المسجلين:\n'
                for line in lines:
                    if len(buf) + len(line) + 1 > 3800: chunks.append(buf); buf = ''
                    buf += line + '\n'
                chunks.append(buf)
                for chunk in chunks: await msg.reply_text(chunk)
            return
        if not dist.get('active'):
            await send_marked(msg, 'error', 'التوزيع متوقف بالفعل')
            return
        dist['active'] = False
        save_data()
        await send_marked(msg, 'stop', f"تم إيقاف التسجيل. إجمالي المسجلين: {len(dist['registrations'])}")
        return

    # A plain number from an admin selects that registration in the latest active distribution
    # where the number exists. Replying is not required.
    if re.fullmatch(r'\d+', text):
        if not await is_admin(update, context): return
        number = int(text)
        candidates = [d for d in data.values() if d.get('chat_id') == chat.id and d.get('active')]
        candidates.sort(key=lambda d: d.get('source_message_id', 0), reverse=True)
        for dist in candidates:
            if 1 <= number <= len(dist['registrations']):
                reg = dist['registrations'][number-1]
                if reg['number'] != number: continue
                await context.bot.send_message(chat_id=chat.id, text='وصل دورك ✅ اقبل وجون 🎉🤩',
                                               reply_to_message_id=reg['message_id'])
                return
        return

    # Registration: only a reply to an active distribution's original message.
    k = reply_key(msg)
    dist = data.get(k) if k else None
    if not dist or not dist.get('active'): return
    if user.id == dist.get('owner_id'): return
    existing = dist.get('user_ids', {}).get(str(user.id))
    if existing:
        await msg.reply_text(f"أنت مسجل من قبل، رقمك هو {existing}.")
        return
    game_id = text
    if len(game_id) > 100 or len(game_id) < 2:
        await send_marked(msg, 'error', 'أرسل ID صحيحاً بالرد على الرسالة الأصلية')
        return
    number = len(dist['registrations']) + 1
    display = user.full_name or user.username or str(user.id)
    reg = {'number': number, 'user_id': user.id, 'display': display,
           'username': user.username or '', 'game_id': game_id, 'message_id': msg.message_id}
    dist['registrations'].append(reg)
    dist.setdefault('user_ids', {})[str(user.id)] = number
    save_data()
    await msg.reply_text(f'تم تسجيلك، رقمك هو {number}.')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception('Unhandled bot error', exc_info=context.error)


def main():
    if not TOKEN:
        raise RuntimeError('Missing TELEGRAM_BOT_TOKEN environment variable')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(error_handler)
    log.info('RDO distribution bot starting with polling')
    app.run_polling(drop_pending_updates=False)

if __name__ == '__main__': main()
