import asyncio
import os
import discord
import zhconv
from discord import app_commands
from dotenv import load_dotenv
from scraper import get_operator_data, load_operator_names, search_operator_names, RARITY_STARS

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

RARITY_COLORS = {
    "1": 0x808080,
    "2": 0x1EAD2C,
    "3": 0x0099FF,
    "4": 0x9B59B6,
    "5": 0xFFD700,
    "6": 0xFF6A00,
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


async def operator_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not current:
        return []
    results = await asyncio.to_thread(search_operator_names, current)
    return [
        app_commands.Choice(name=zhconv.convert(name, "zh-hant"), value=name)
        for name in results
    ]


@tree.command(name="幹員資料", description="查詢明日方舟幹員基本資料")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使、推進之王")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_info(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)

    data = get_operator_data(幹員名稱)

    if not data:
        embed = discord.Embed(
            description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。\n繁體與簡體均可，例如：銀灰、银灰、能天使",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed)
        return

    rarity = data.get("rarity", "")
    color = RARITY_COLORS.get(rarity, 0x7289DA)
    stars = RARITY_STARS.get(rarity, rarity)

    embed = discord.Embed(
        title=f"📋 {data.get('name', 幹員名稱)}",
        color=color,
        url=f"https://prts.wiki/w/{幹員名稱}",
    )

    # 基本資訊
    if stars:
        embed.add_field(name="稀有度", value=stars, inline=True)
    if data.get("job_class"):
        embed.add_field(name="職業", value=data["job_class"], inline=True)
    if data.get("branch"):
        embed.add_field(name="分支", value=data["branch"], inline=True)
    if data.get("country"):
        embed.add_field(name="所屬國家", value=data["country"], inline=True)
    if data.get("organization"):
        embed.add_field(name="所屬組織", value=data["organization"], inline=True)
    if data.get("tags"):
        embed.add_field(name="標籤", value=data["tags"], inline=True)
    if data.get("trait"):
        embed.add_field(name="特性", value=data["trait"], inline=False)

    # 基礎數值
    stats = []
    if data.get("hp"):
        stats.append(f"HP {data['hp']}")
    if data.get("atk"):
        stats.append(f"攻擊 {data['atk']}")
    if data.get("defense"):
        stats.append(f"防禦 {data['defense']}")
    if data.get("res"):
        stats.append(f"法抗 {data['res']}")
    if data.get("block"):
        stats.append(f"阻擋 {data['block']}")
    if data.get("cost"):
        stats.append(f"費用 {data['cost']}")
    if data.get("redeploy"):
        stats.append(f"再部署 {data['redeploy']}秒")
    if stats:
        embed.add_field(name="基礎數值（精二滿級）", value=" ｜ ".join(stats), inline=False)

    # 製作人員
    credits = []
    if data.get("artist"):
        credits.append(f"畫師：{data['artist']}")
    if data.get("cn_va"):
        credits.append(f"中文CV：{data['cn_va']}")
    if data.get("jp_va"):
        credits.append(f"日文CV：{data['jp_va']}")
    if credits:
        embed.add_field(name="製作人員", value="　".join(credits), inline=False)

    if data.get("img_base"):
        embed.set_thumbnail(url=data["img_base"])
    if data.get("img_elite2"):
        embed.set_image(url=data["img_elite2"])

    embed.set_footer(text="資料來源：PRTS Wiki｜使用 /幹員檔案 查詢背景故事")

    await interaction.followup.send(embed=embed)


@tree.command(name="幹員檔案", description="查詢幹員背景故事（檔案一～四）")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_lore(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)

    data = get_operator_data(幹員名稱)

    if not data:
        embed = discord.Embed(
            description=f"❌ 找不到幹員「{幹員名稱}」的資料。",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed)
        return

    has_lore = any(data.get(f"file{i}") for i in range(1, 5))
    if not has_lore:
        await interaction.followup.send(f"「{data.get('name', 幹員名稱)}」目前沒有檔案資料。")
        return

    embed = discord.Embed(
        title=f"📖 {data.get('name', 幹員名稱)}｜幹員檔案",
        color=RARITY_COLORS.get(data.get("rarity", ""), 0x7289DA),
        url=f"https://prts.wiki/w/{幹員名稱}",
    )

    for i in range(1, 5):
        content = data.get(f"file{i}", "")
        if content:
            # Discord embed field value 限制 1024 字元
            if len(content) > 1000:
                content = content[:1000] + "…（詳見 PRTS Wiki）"
            embed.add_field(name=f"檔案{i}", value=content, inline=False)

    embed.set_footer(text="資料來源：PRTS Wiki")
    await interaction.followup.send(embed=embed)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot 已上線：{client.user}（ID: {client.user.id}）")
    print("📡 斜線指令已同步，首次使用可能需要幾分鐘生效")
    asyncio.create_task(asyncio.to_thread(load_operator_names))
    print("⏳ 正在背景載入幹員清單...")


client.run(TOKEN)
