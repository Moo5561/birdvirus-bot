import logging
import runpy
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from discord.ext import commands


class DiscordRegistrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with (
            patch.object(commands.AutoShardedBot, "run", autospec=True) as run,
            patch("bot.config.token", "MTIz.offline.test"),
            patch.object(sys, "argv", ["main.py", "--host", "offline-test"]),
            patch.object(logging, "basicConfig"),
            patch.object(logging, "FileHandler"),
        ):
            runpy.run_module("main", run_name="__main__")
        run.assert_called_once()
        self.client = run.call_args.args[0]
        self.client._connection.application_id = 123

    async def test_global_sync_includes_dms_and_personal_installs(self):
        upload = AsyncMock(return_value=[])
        with patch.object(self.client.tree._http, "bulk_upsert_global_commands", upload):
            await self.client.tree.sync()
        upload.assert_awaited_once()
        self.assertEqual(upload.await_args.args, (123,))
        payload = {command["name"]: command for command in upload.await_args.kwargs["payload"]}
        guild_only = {"bad", "leaderboard", "play", "property", "stop", "vc"}
        expected = guild_only | {"balance", "chat", "httpbird", "internet", "ping"}
        self.assertLessEqual(expected, payload.keys())
        for name, command in payload.items():
            with self.subTest(command=name):
                self.assertEqual(command["contexts"], [0] if name in guild_only else [0, 1, 2])
                self.assertEqual(command["integration_types"], [0] if name in guild_only else [0, 1])
        self.assertIn("httpcat", {subcommand["name"] for subcommand in payload["internet"]["options"]})

    async def test_personal_install_does_not_inherit_server_admin_access(self):
        author = SimpleNamespace(id=123, guild_permissions=SimpleNamespace(administrator=True))
        interaction = Mock(is_guild_integration=Mock(return_value=False))
        ctx = SimpleNamespace(author=author, guild=object(), interaction=interaction)
        predicate = self.client.get_command("property register").checks[0]
        with patch("bot.commands._is_configured_admin", AsyncMock(return_value=False)):
            self.assertFalse(await predicate(ctx))
            interaction.is_guild_integration.return_value = True
            self.assertTrue(await predicate(ctx))
        with patch("bot.commands._is_configured_admin", AsyncMock(return_value=True)):
            ctx.guild = None
            self.assertTrue(await predicate(ctx))

    async def test_slash_ban_check_applies_in_private_channels(self):
        with patch("bot.bans.read_banned_users", AsyncMock(return_value={123})):
            self.assertFalse(await self.client.tree.interaction_check(Mock(user=Mock(id=123))))
            self.assertTrue(await self.client.tree.interaction_check(Mock(user=Mock(id=456))))

    async def test_say_uses_interaction_reply_for_a_personal_install(self):
        ctx = Mock(
            interaction=Mock(is_user_integration=Mock(return_value=True)),
            author=SimpleNamespace(id=123, name="bird"),
            reply=AsyncMock(),
        )
        with patch("bot.db.log_say") as log_say:
            await self.client.get_command("say").callback(ctx, "hello")
        log_say.assert_called_once_with(123, "bird", "hello")
        ctx.reply.assert_awaited_once()
        self.assertEqual(ctx.reply.await_args.args, ("hello",))
        self.assertEqual(ctx.reply.await_args.kwargs["allowed_mentions"].to_dict(), {"parse": []})
        ctx.channel.send.assert_not_called()
