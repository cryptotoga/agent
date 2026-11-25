import os
import time
import asyncio
import tempfile
import aiohttp
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from google.genai.errors import APIError
import edge_tts
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")

# 우선순위 모델 리스트 (1순위 혼잡 시 자동으로 다음 모델로 전환)
MODEL_CANDIDATES = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.8-flash']
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
You are a friendly, natural native English conversation partner on a voice call.
1. Listen directly to the user's audio (or read their text) and reply naturally in spoken English (2-3 concise sentences).
2. NEVER use markdown formatting (no asterisks, bullet points, or emojis) because your response will be read aloud by a text-to-speech engine.
3. If the user makes a noticeable grammar error or unnatural phrasing, gently give a brief, spoken tip at the end.
4. Always end with a short, engaging follow-up question.
"""

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
# 대화 히스토리 직접 관리 (모델이 중간에 바뀌어도 대화 맥락 100% 유지)
user_histories: dict[int, list[types.Content]] = {}


def generate_with_retry_and_fallback(user_id: int, user_parts: list) -> str:
    """503 혼잡 시 자동 재시도 및 예비 모델로 전환하며 대화 맥락 유지"""
    history = user_histories.setdefault(user_id, [])
    current_turn = types.Content(role="user", parts=user_parts)
    contents = history + [current_turn]

    last_error = None
    for model_name in MODEL_CANDIDATES:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                    ),
                )
                reply_text = response.text.strip()
                # 성공 시 대화 기록에 사용자 입력과 AI 응답 저장 (최근 20턴 유지)
                history.append(current_turn)
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=reply_text)]))
                if len(history) > 40:
                    user_histories[user_id] = history[-40:]
                return reply_text

            except APIError as e:
                last_error = e
                if e.code == 503:
                    wait_sec = 1.5 * (attempt + 1)
                    print(f"⚠️ [{model_name}] 서버 혼잡(503). {wait_sec}초 후 재시도 ({attempt + 1}/3)...")
                    time.sleep(wait_sec)
                    continue
                elif e.code == 404:
                    print(f"⚠️ [{model_name}] 모델을 찾을 수 없어 다음 예비 모델로 전환합니다.")
                    break
                else:
                    raise e
    raise last_error


async def speak_in_voice(vc: discord.VoiceClient, text: str):
    if not vc or not vc.is_connected():
        return

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    communicate = edge_tts.Communicate(text, voice=TTS_VOICE)
    await communicate.save(tmp_path)

    done_event = asyncio.Event()

    def after_play(error):
        if error:
            print(f"[재생 오류] {error}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        bot.loop.call_soon_threadsafe(done_event.set)

    while vc.is_playing():
        await asyncio.sleep(0.1)

    vc.play(discord.FFmpegPCMAudio(tmp_path), after=after_play)
    await done_event.wait()


@bot.event
async def on_ready():
    print(f"✅ 로그인 완료: {bot.user} (503 자동 재시도 및 폴백 활성화)")


@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("먼저 디스코드 음성 채널에 입장해 주세요!")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"🎙️ **{channel.name}** 연결 완료! 음성 메시지나 영어로 말을 걸어보세요.")


@bot.command()
async def reset(ctx):
    user_histories.pop(ctx.author.id, None)
    await ctx.send("🔄 대화 기억을 초기화했습니다.")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith("!"):
        return await bot.process_commands(message)

    vc = message.guild.voice_client if message.guild else None
    if not vc or not vc.is_connected():
        return

    user_id = message.author.id
    audio_attachment = next(
        (a for a in message.attachments if (a.content_type and "audio" in a.content_type) or a.filename.endswith((".ogg", ".mp3", ".wav", ".m4a"))),
        None,
    )

    try:
        async with message.channel.typing():
            if audio_attachment:
                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_attachment.url) as resp:
                        audio_bytes = await resp.read()

                mime = audio_attachment.content_type or "audio/ogg"
                user_parts = [
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                    types.Part.from_text(text="Reply naturally to what I just said."),
                ]
            elif message.content.strip():
                user_parts = [types.Part.from_text(text=message.content.strip())]
            else:
                return

            reply_text = await asyncio.to_thread(
                generate_with_retry_and_fallback, user_id, user_parts
            )

            await message.channel.send(f"🤖 **Tutor:** {reply_text}")
            await speak_in_voice(vc, reply_text)

    except Exception as e:
        print(f"[오류] {e}")
        await message.channel.send(f"⚠️ 오류가 발생했습니다: `{e}`")


@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 음성 채널에서 퇴장했습니다.")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
