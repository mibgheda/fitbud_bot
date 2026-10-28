"""
HTTP-API для команды iPhone «FitBud»: приём данных из Apple Health.

POST /health/v1/sync  — заголовок X-FitBud-Key: <ключ из бота>, тело — JSON (формат в utils/health.py)
GET  /health/v1/ping  — проверка, что сервер доступен

Работает в одном процессе с ботом; HTTPS даёт Caddy (deploy/Caddyfile).
"""
import json
import logging
import time
from collections import defaultdict, deque

from aiohttp import web

from database.database import async_session, HealthDevice
from utils import diary, health
from utils.daytime import utc_now

logger = logging.getLogger(__name__)

RATE_LIMIT = 30  # запросов в час на один ключ
_requests = defaultdict(deque)


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = _requests[key]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return True
    window.append(now)
    return False


def _reply(ok: bool, message: str, status: int = 200) -> web.Response:
    return web.json_response({'ok': ok, 'message': message}, status=status,
                             dumps=lambda data: json.dumps(data, ensure_ascii=False))


async def ping(request: web.Request) -> web.Response:
    return _reply(True, 'FitBud на связи')


async def sync(request: web.Request) -> web.Response:
    token = request.headers.get('X-FitBud-Key', '').strip()
    device = await health.device_by_token(token)
    if not device:
        return _reply(False, 'Ключ не подходит. Получи новый в боте: Мой профиль → ⌚ Часы.', 401)
    if _rate_limited(device.token_hash):
        return _reply(False, 'Слишком часто. Попробуй позже.', 429)
    if request.content_length and request.content_length > health.MAX_BODY_BYTES:
        return _reply(False, 'Слишком много данных за раз.', 413)
    try:
        payload = json.loads(await request.text())
    except (ValueError, UnicodeDecodeError):
        return _reply(False, 'Не получилось прочитать данные.', 400)
    if not isinstance(payload, dict):
        return _reply(False, 'Не получилось прочитать данные.', 400)

    user = await diary.get_user(device.user_id)
    if not user:
        return _reply(False, 'Аккаунт в боте не найден. Нажми /start в боте.', 404)

    try:
        summary = await health.store_payload(user, payload)
    except Exception:
        logger.exception("Ошибка сохранения данных с часов")
        return _reply(False, 'Ошибка на сервере, попробуем в следующий раз.', 500)

    async with async_session() as session:
        stored = await session.get(HealthDevice, device.id)
        stored.last_sync_at = utc_now()
        await session.commit()

    new_workouts = summary['new_workouts']
    if new_workouts:
        from handlers.watch import notify_new_workouts
        await notify_new_workouts(request.app['bot'], user, new_workouts)

    logger.info("Часы: user=%s показателей=%s тренировок=%s", user.telegram_id,
                summary['metrics'], len(new_workouts))
    message = f"Получено показателей: {summary['metrics']}"
    if new_workouts:
        message += f", новых тренировок: {len(new_workouts)}"
    return _reply(True, message)


def create_app(bot) -> web.Application:
    app = web.Application(client_max_size=health.MAX_BODY_BYTES)
    app['bot'] = bot
    app.router.add_get('/health/v1/ping', ping)
    app.router.add_post('/health/v1/sync', sync)
    return app


async def start(bot, port: int) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', port).start()
    logger.info("API для часов слушает порт %s", port)
    return runner
