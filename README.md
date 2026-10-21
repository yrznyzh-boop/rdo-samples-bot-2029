# RDO Distribution Telegram Bot

## Features
- Only Telegram group administrators/creator can start, list, stop, or select a turn.
- Start by replying `توزيع` to the admin's own original group message.
- Members register by replying to that original message with their game ID.
- Each Telegram account can register once per distribution. Re-registering returns the existing number.
- `قائمة` and `وقف توزيع` must be sent as replies to that distribution's original message.
- An admin can send a registration number as a normal, non-reply message. The bot selects that number in the newest active distribution in the group and replies to the registered member's ID message with `وصل دورك...`.
- Multiple independent distributions can be active in the same group.
- State is stored in `data.json`.

## Deploy
1. Upload `main.py` and `requirements.txt` to your GitHub repository (replace the old files).
2. Set the host environment variable `TELEGRAM_BOT_TOKEN` to the token from BotFather. Never put the token in GitHub or share it.
3. Ensure the host runs `python main.py` and installs `requirements.txt`.
4. Add the bot to the Telegram group and make it an administrator. It needs permission to send messages; it does not need permission to delete messages or ban users.
5. Keep persistent storage for `data.json`; if the host's filesystem is ephemeral, registrations may be lost on restart.

## Optional custom emoji
The URLs `t.me/addemoji/...` are custom-emoji packs, not ordinary sticker packs. A pack URL alone does not provide the numeric `custom_emoji_id` values required by the Bot API. After obtaining IDs for selected emoji, set optional environment variables:
- `EMOJI_START`, `EMOJI_REGISTERED`, `EMOJI_TURN`, `EMOJI_LIST`, `EMOJI_STOP`, `EMOJI_ERROR`

Each variable must contain a numeric custom emoji ID. If unset, the bot uses ordinary text emoji as a fallback. The account owner's Telegram Premium subscription does not automatically grant the bot these IDs or make it able to send arbitrary custom emoji.

## Important behavior for numeric turn selection
When multiple distributions are active, a plain number selects that number in the newest active distribution that contains it. To avoid ambiguity, use one active distribution at a time in a group, or stop older distributions before selecting turns.
