# Gets the required amount of xp to level up from [level - 1] to [level], or 0 if it surpasses it
from math import ceil
import re
import time as t

import discord
from discord import Forbidden
from discord.ext import commands, bridge
from discord.ext.bridge import BridgeContext
from discord.utils import get as find

from app import client
from app.types.discord import DiscordMember, DiscordChannelType, DiscordObject, DiscordRole
from app.database.models import Member
from app.database.models import Rank
from app.config import config
from app.cache import cache_get, cache_set
from app.utilities import logger, defer


def get_required_xp_for_level(level, current_xp=0):
    required_xp = ceil(1.0 * (level**2) + 4.8 * level + 596)  # 1.048596
    return (required_xp - current_xp) if (required_xp > current_xp) else 0


# Table of example values:
# Level  |     XP  |     Total
#   1    |    596  |       596
#   2    |    602  |     1 204
#   3    |    610  |     1 830
#   4    |    620  |     2 480
#   5    |    632  |     3 160
#  10    |    721  |     7 210
#  15    |    860  |    12 900
#  20    |  1 049  |    20 980
#  25    |  1 288  |    32 200
#  50    |  3 233  |   161 650
# 100    | 10 873  | 1 087 300


class RankSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def handle_rank_up(self, member: DiscordMember, level: int):
        if member is not None:
            rank = Rank.get_rank(member.guild, level)

            if rank is not None:
                try:
                    # DiscordObject is actually a Snowflake, but Pycord is too shy to admit it
                    await member.add_roles(DiscordObject(rank.role_id), reason=f"User has reached level {level}.")
                except Forbidden:
                    logger.warning(f"Tried to assign role to user {member.name}#{member.discriminator} ({member.id}) but missing permission! {rank}")
                finally:
                    if rank.message is not None:
                        msg = rank.message.replace("{level}", str(level)).replace("{name}", member.display_name)
                        await member.send(f"From {member.guild.name}: {msg}")
                        return  # Return to not call a second message

            # If we don't have a rank, or the rank has no message, default to this one:
            await member.send(f"From {member.guild.name}: Congrats on ranking up to level {level}!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id == self.bot.user.id:
            return  # Don't allow self-tracking
        if message.channel.type != DiscordChannelType.text:
            return  # Only track in guild text channels

        print(message.content)

        curr_time = int(t.time())

        last_xp_timestamp = int(cache_get("ranking-timeout", 0, message.guild, message.author))

        if (curr_time - last_xp_timestamp) >= config.RANK_XP_TIMEOUT:
            cache_set("ranking-timeout", curr_time, message.guild, message.author)

            member = Member.get_member(message.guild.id, message.author.id)

            member.xp += config.RANK_XP_REWARD

            required_xp = get_required_xp_for_level(member.level)

            if member.xp >= required_xp:
                member.xp -= required_xp
                member.level += 1
                await self.handle_rank_up(message.author, member.level)

            member.save()


    @bridge.bridge_command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @discord.option(name="level", description="The level at which to unlock this rank. Must be a number.")
    @discord.option(name="role", description="The role to apply. Can be the id, name, or role itself.")
    @discord.option(name="message", description="An optional custom message to send when a {user} reaches this rank {level}.")
    async def rank_create(self, ctx: BridgeContext, level: int, role: str, message:str = None):
        """Creates a rank with a role tied to it. Additionally binds a message."""
        await defer(ctx)

        # Find the role from the information given
        match = re.search(r"^\d+$", role)  # Raw Snowflake ID match.
        if match is not None:
            # We have a Snowflake id!
            role = int(match.group(0))

        else:
            match = re.search(r"(?:^<@&(\d+)>$)", role)  #
            if match is not None:
                # We have a discord-formatted role id! Group 0 is the snowflake of the role
                role = int(match.group(1))
            else:
                # Check if it's a role's name. If it isn't, the role is None and it doesn't exist
                role = find(ctx.guild.roles, name=role)
                if role is not None:
                    role = role.id

        if role is None:
            await ctx.respond("An invalid role was provided.")
            return

        if Rank.get_rank(ctx.guild, role_id=role) is not None:
            await ctx.respond("This rank was already set! Please remove it before trying to add a new one.")
            return

        # Create rank object. We're avoiding Rank.get_rank to also initialize the message field
        rank = Rank(level=level, gid=ctx.guild.id, role_id=role, message=message)

        if rank is not None:
            rank.save()
            await ctx.respond("Rank created.")

        else:
            await ctx.respond("Rank could not be created.")

    @bridge.bridge_command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @discord.option(name="level", description="The level at which to unlock this rank. Must be a number.")
    async def rank_remove(self, ctx: BridgeContext, level:int):
        """Removes a rank from the database if it exists."""
        await defer(ctx)

        rank = Rank.get_rank(ctx.guild, level=level)

        if rank is not None:
            rank.delete()
            await ctx.respond(f"Rank {level} has been deleted.")

        else:
            await ctx.respond(f"No rank was found for level {level}.")


def setup(bot: client.PhoneWave):
    bot.add_cog(RankSystem(bot))
