import discord
from discord.ext import commands
import logging
from datetime import datetime, timedelta
import json
import asyncio
import aiofiles
import os
from run_onnx import analyze_image

# Configuration
TOKEN = "YOUR_DISCORD_BOT_TOKEN" # Always use process.env for such sensitive information
NSFW_THRESHOLD = 0.5 # for better accuracy
MAX_TIMEOUT_DURATION = timedelta(hours=6)
DATA_FILE = "moderation_data.json"

# setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ImageModerator")

# bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

class ModerationData:
    """Handles data persistence for moderation settings"""
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.data = {
            'enabled_servers': {},  # {server_id: True/False}
            'user_warnings': {},    # {server_id: {user_id: count}}
            'moderation_log': []
        }
    
    async def load_data(self):
        """Load data from file with proper initialization"""
        try:
            if os.path.exists(self.data_file):
                async with aiofiles.open(self.data_file, 'r') as f:
                    content = await f.read()
                    loaded_data = json.loads(content)
                    
                    # ensure all required keys exist
                    self.data = {
                        'enabled_servers': loaded_data.get('enabled_servers', {}),
                        'user_warnings': loaded_data.get('user_warnings', {}),
                        'moderation_log': loaded_data.get('moderation_log', [])
                    }
                    logger.info("Moderation data loaded successfully")
            else:
                # create new file with default structure
                await self.save_data()
                logger.info("Created new moderation data file")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            # initialize with default structure if loading fails
            self.data = {
                'enabled_servers': {},
                'user_warnings': {},
                'moderation_log': []
            }
            await self.save_data()
    
    async def save_data(self):
        """Save data to file"""
        try:
            async with aiofiles.open(self.data_file, 'w') as f:
                await f.write(json.dumps(self.data, indent=2))
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def is_enabled(self, guild_id: int) -> bool:
        """Check if moderation is enabled in a server"""
        # ensure the key exists before accessing
        if 'enabled_servers' not in self.data:
            self.data['enabled_servers'] = {}
        return self.data['enabled_servers'].get(str(guild_id), False)
    
    def set_enabled(self, guild_id: int, enabled: bool):
        """Enable/disable moderation in a server"""
        # ensure the key exists before accessing
        if 'enabled_servers' not in self.data:
            self.data['enabled_servers'] = {}
        self.data['enabled_servers'][str(guild_id)] = enabled
    
    def get_user_warnings(self, guild_id: int, user_id: int) -> int:
        """Get warning count for user in specific server"""
        # ensure the key exists before accessing
        if 'user_warnings' not in self.data:
            self.data['user_warnings'] = {}
        
        server_warnings = self.data['user_warnings'].get(str(guild_id), {})
        return server_warnings.get(str(user_id), 0)
    
    def increment_warning(self, guild_id: int, user_id: int):
        """Increment warning count for user in specific server"""
        # esure the key exists before accessing
        if 'user_warnings' not in self.data:
            self.data['user_warnings'] = {}
        
        guild_id_str = str(guild_id)
        user_id_str = str(user_id)
        
        if guild_id_str not in self.data['user_warnings']:
            self.data['user_warnings'][guild_id_str] = {}
        
        self.data['user_warnings'][guild_id_str][user_id_str] = self.get_user_warnings(guild_id, user_id) + 1
    
    def reset_warnings(self, guild_id: int = None, user_id: int = None):
        """Reset warnings for server or user"""
        # esure the key exists before accessing
        if 'user_warnings' not in self.data:
            self.data['user_warnings'] = {}
            return
        
        if guild_id and user_id:
            # reset specific user in specific server
            guild_id_str = str(guild_id)
            user_id_str = str(user_id)
            if guild_id_str in self.data['user_warnings'] and user_id_str in self.data['user_warnings'][guild_id_str]:
                del self.data['user_warnings'][guild_id_str][user_id_str]
        elif guild_id:
            # reset all users in specific server
            guild_id_str = str(guild_id)
            if guild_id_str in self.data['user_warnings']:
                self.data['user_warnings'][guild_id_str] = {}
        else:
            # reset everything
            self.data['user_warnings'] = {}

class EscalationSystem:
    """Handles timeout escalation based on warning history"""
    
    TIMEOUT_LEVELS = {
        1: timedelta(minutes=10),    # First offense
        2: timedelta(hours=1),       # Second offense
        3: timedelta(hours=3),       # Third offense
        4: timedelta(hours=6),       # Fourth+ offense (max), you can increase the timeout duration
    }
    
    @classmethod
    def calculate_timeout(cls, warning_count: int) -> timedelta:
        """Calculate timeout duration based on warning count"""
        return cls.TIMEOUT_LEVELS.get(min(warning_count, 4), cls.TIMEOUT_LEVELS[4])
    
    @classmethod
    def format_duration(cls, duration: timedelta) -> str:
        """Format timedelta to human-readable string"""
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m"
        return f"{int(minutes)}m"

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='',
            intents=intents,
            help_command=None
        )
        self.data_manager = ModerationData(DATA_FILE)
    
    async def setup_hook(self):
        """Called when bot is starting"""
        logger.info("Bot is starting up...")
        await self.data_manager.load_data()

    async def close(self):
        """Called when bot is shutting down"""
        await self.data_manager.save_data()
        await super().close()

# initialize bot
bot = ModerationBot()

async def safe_delete_message(message: discord.Message) -> bool:
    """Safely delete a message"""
    try:
        await message.delete()
        return True
    except discord.Forbidden:
        logger.warning(f"Missing permissions to delete message")
        return False
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return False

async def safe_timeout_user(member: discord.Member, duration: timedelta, score: float) -> bool:
    """Safely timeout a user"""
    try:
        await member.timeout(
            duration, 
            reason=f"NSFW image detected (score: {score:.3f})"
        )
        return True
    except discord.Forbidden:
        logger.warning(f"Missing permissions to timeout {member}")
        return False
    except Exception as e:
        logger.error(f"Error timing out user: {e}")
        return False

async def handle_nsfw_infraction(message: discord.Message, score: float):
    """Handle NSFW content with moderation actions"""
    user_id = message.author.id
    guild_id = message.guild.id
    
    # update warning count
    bot.data_manager.increment_warning(guild_id, user_id)
    warning_count = bot.data_manager.get_user_warnings(guild_id, user_id)
    
    # calculate timeout duration
    timeout_duration = EscalationSystem.calculate_timeout(warning_count)
    
    # take moderation actions
    deletion_success = await safe_delete_message(message)
    timeout_success = await safe_timeout_user(message.author, timeout_duration, score)
    
    # create moderation embed
    embed = discord.Embed(
        title="🚨 NSFW Content Detected",
        color=discord.Color.red(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="👤 User", value=message.author.mention, inline=True)
    embed.add_field(name="📊 NSFW Score", value=f"`{score:.3f}`", inline=True)
    embed.add_field(name="⚠️ Warning Count", value=f"`{warning_count}`", inline=True)
    embed.add_field(name="⏰ Timeout Duration", value=EscalationSystem.format_duration(timeout_duration), inline=True)
    embed.add_field(name="🗑️ Message Removed", value="✅" if deletion_success else "❌", inline=True)
    embed.add_field(name="🔇 User Timed Out", value="✅" if timeout_success else "❌", inline=True)
    
    if warning_count >= 4:
        embed.add_field(
            name="💀 Maximum Escalation", 
            value="User has reached maximum timeout duration", 
            inline=False
        )
    
    embed.set_footer(text="Automated Moderation System")
    
    # send moderation embed
    await message.channel.send(embed=embed)
    
    # save data
    await bot.data_manager.save_data()

@bot.event
async def on_ready():
    logger.info(f"✅ {bot.user} is online!")
    
    # count enabled servers
    enabled_count = 0
    if hasattr(bot.data_manager, 'data') and 'enabled_servers' in bot.data_manager.data:
        enabled_count = len([s for s in bot.data_manager.data['enabled_servers'].values() if s])
    
    logger.info(f"🛡️ Moderation enabled in {enabled_count} servers")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for NSFW content 👀"))

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # process commands
    await bot.process_commands(message)
    
    # check if message is in a guild and moderation is enabled
    if not message.guild:
        return
    
    # check for enabled servers
    try:
        if not bot.data_manager.is_enabled(message.guild.id):
            return
    except Exception as e:
        logger.error(f"Error checking server status: {e}")
        return

    # check message attachments for images
    for attachment in message.attachments:
        if attachment.content_type and "image" in attachment.content_type:
            url = attachment.url
            score = analyze_image(url)

            # handle analysis errors
            if score == -1:
                continue

            # handle NSFW content
            if score > NSFW_THRESHOLD:
                await handle_nsfw_infraction(message, score)
                break
            
            

# command groups
@bot.group(name='mod', invoke_without_command=True)
async def moderation_group(ctx: commands.Context):
    """Moderation system management commands"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need **Administrator** permissions to use moderation commands.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    is_enabled = bot.data_manager.is_enabled(ctx.guild.id)
    
    embed = discord.Embed(
        title="🛡️ Image Moderation System",
        description="AI-powered content moderation for this server",
        color=discord.Color.blue()
    )
    
    status = "🟢 **ENABLED**" if is_enabled else "🔴 **DISABLED**"
    embed.add_field(name="Server Status", value=status, inline=True)
    embed.add_field(name="NSFW Threshold", value=f"`{NSFW_THRESHOLD}`", inline=True)
    
    # get server specific warnings
    server_warnings = bot.data_manager.data.get('user_warnings', {}).get(str(ctx.guild.id), {})
    active_warnings = len(server_warnings)
    embed.add_field(name="Active Warnings", value=f"`{active_warnings}`", inline=True)
    
    embed.add_field(
        name="Available Commands", 
        value=(
            "`:mod enable` - Enable moderation in this server\n"
            "`:mod disable` - Disable moderation in this server\n"
            "`:mod status` - Server status\n"
            "`:mod warnings [user]` - Check warnings\n"
            "`:mod reset [user]` - Reset warnings\n"
            "`:mod help` - Command help"
        ), 
        inline=False
    )
    
    embed.set_footer(text="All commands require Administrator permissions")
    await ctx.send(embed=embed)

@moderation_group.command(name='enable')
async def enable_moderation(ctx: commands.Context):
    """Enable the image moderation system in this server"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need **Administrator** permissions to enable moderation.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    bot.data_manager.set_enabled(ctx.guild.id, True)
    await bot.data_manager.save_data()
    
    embed = discord.Embed(
        title="✅ Moderation Enabled",
        description="Image moderation system is now **ACTIVE** in this server",
        color=discord.Color.green()
    )
    embed.add_field(name="Status", value="🟢 **ENABLED**", inline=True)
    embed.add_field(name="NSFW Threshold", value=f"`{NSFW_THRESHOLD}`", inline=True)
    embed.add_field(name="Action", value="Scanning all images for NSFW content", inline=True)
    
    await ctx.send(embed=embed)
    logger.info(f"Moderation enabled in {ctx.guild.name} by {ctx.author}")

@moderation_group.command(name='disable')
async def disable_moderation(ctx: commands.Context):
    """Disable the image moderation system in this server"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need **Administrator** permissions to disable moderation.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    bot.data_manager.set_enabled(ctx.guild.id, False)
    await bot.data_manager.save_data()
    
    embed = discord.Embed(
        title="🔴 Moderation Disabled",
        description="Image moderation system is now **INACTIVE** in this server",
        color=discord.Color.orange()
    )
    embed.add_field(name="Status", value="🔴 **DISABLED**", inline=True)
    embed.add_field(name="Action", value="No images will be scanned", inline=True)
    
    await ctx.send(embed=embed)
    logger.info(f"Moderation disabled in {ctx.guild.name} by {ctx.author}")

@moderation_group.command(name='status')
async def moderation_status(ctx: commands.Context):
    """Show moderation system status for this server"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    embed = discord.Embed(
        title="📊 Moderation System Status",
        description=f"Status for **{ctx.guild.name}**",
        color=discord.Color.blue()
    )
    
    is_enabled = bot.data_manager.is_enabled(ctx.guild.id)
    status = "🟢 **ENABLED**" if is_enabled else "🔴 **DISABLED**"
    embed.add_field(name="System Status", value=status, inline=True)
    embed.add_field(name="NSFW Threshold", value=f"`{NSFW_THRESHOLD}`", inline=True)
    
    # Server specific statistics 
    server_warnings = bot.data_manager.data.get('user_warnings', {}).get(str(ctx.guild.id), {})
    total_warnings = sum(server_warnings.values())
    unique_users = len(server_warnings)
    embed.add_field(name="Total Warnings", value=f"`{total_warnings}`", inline=True)
    embed.add_field(name="Warned Users", value=f"`{unique_users}`", inline=True)
    
    await ctx.send(embed=embed)

@moderation_group.command(name='warnings')
async def check_warnings(ctx: commands.Context, user: discord.Member = None):
    """Check warning count for a user or all users in this server"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    if user:
        warning_count = bot.data_manager.get_user_warnings(ctx.guild.id, user.id)
        embed = discord.Embed(color=discord.Color.orange())
        embed.add_field(name="👤 User", value=user.mention, inline=True)
        embed.add_field(name="⚠️ Warnings", value=f"`{warning_count}`", inline=True)
        
        if warning_count > 0:
            next_timeout = EscalationSystem.calculate_timeout(warning_count + 1)
            embed.add_field(name="⏰ Next Timeout", value=EscalationSystem.format_duration(next_timeout), inline=True)
        
        await ctx.send(embed=embed)
    else:
        server_warnings = bot.data_manager.data.get('user_warnings', {}).get(str(ctx.guild.id), {})
        if not server_warnings:
            await ctx.send("📭 No warnings recorded in this server.")
            return
        
        # show top 10 warned users
        sorted_warnings = sorted(server_warnings.items(), key=lambda x: int(x[1]), reverse=True)[:10]
        
        embed = discord.Embed(
            title="⚠️ User Warning Leaderboard",
            description=f"Top warned users in **{ctx.guild.name}**",
            color=discord.Color.orange()
        )
        
        for user_id, count in sorted_warnings:
            try:
                user_obj = await bot.fetch_user(int(user_id))
                username = user_obj.name
            except:
                username = f"Unknown ({user_id})"
            
            timeout_duration = EscalationSystem.calculate_timeout(count)
            embed.add_field(
                name=username, 
                value=f"Warnings: `{count}` | Timeout: `{EscalationSystem.format_duration(timeout_duration)}`", 
                inline=False
            )
        
        await ctx.send(embed=embed)

@moderation_group.command(name='reset')
async def reset_warnings(ctx: commands.Context, user: discord.Member = None):
    """Reset warnings for a user or all users in this server"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in a server.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need **Administrator** permissions to reset warnings.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if user:
        bot.data_manager.reset_warnings(ctx.guild.id, user.id)
        embed = discord.Embed(
            title="✅ Warnings Reset",
            description=f"Warnings have been reset for {user.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        logger.info(f"Warnings reset for {user} in {ctx.guild.name} by {ctx.author}")
    else:
        bot.data_manager.reset_warnings(ctx.guild.id)
        embed = discord.Embed(
            title="✅ All Warnings Reset",
            description="All warnings have been reset in this server",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        logger.info(f"All warnings reset in {ctx.guild.name} by {ctx.author}")
    
    await bot.data_manager.save_data()

@moderation_group.command(name='help')
async def moderation_help(ctx: commands.Context):
    """Show command help"""
    embed = discord.Embed(
        title="🛡️ Moderation System Help",
        description="AI-powered image moderation commands",
        color=discord.Color.blue()
    )
    
    commands_list = {
        "**:mod enable**": "Enable moderation in this server",
        "**:mod disable**": "Disable moderation in this server", 
        "**:mod status**": "Show server status",
        "**:mod warnings [user]**": "Check warnings for user/all in this server",
        "**:mod reset [user]**": "Reset warnings (user/all) in this server",
        "**:mod help**": "This help message"
    }
    
    for cmd, desc in commands_list.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="🔐 Permissions",
        value="All commands require **Administrator** permissions",
        inline=False
    )
    
    await ctx.send(embed=embed)

# error handling
@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    
    logger.error(f"Command error: {error}")
    
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need **Administrator** permissions to use this command.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Argument",
            description="Please check the command usage and try again.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Command Error",
            description="An unexpected error occurred.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

# starting bot
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
