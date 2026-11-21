import logging
import runpy
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from discord.ext import commands
from discord.ext.commands.view import StringView


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
        option, = payload["httpbird"]["options"]
        self.assertEqual(option["name"], "code")
        self.assertTrue(option["required"])
        self.assertTrue(option["autocomplete"])

    async def test_httpbird_suggests_photos_and_searches_fallback_codes(self):
        from bot.commands.httpbird import _PHOTO_CREDITS

        command = self.client.tree.get_command("httpbird")

        async def suggest(query):
            response = Mock(is_done=Mock(return_value=False), autocomplete=AsyncMock())
            interaction = SimpleNamespace(response=response)
            await command._invoke_autocomplete(interaction, "code", SimpleNamespace(code=query))
            response.autocomplete.assert_awaited_once()
            choices, = response.autocomplete.await_args.args
            self.assertLessEqual(len(choices), 25)
            return {choice.value: choice.name for choice in choices}

        self.assertEqual(set(await suggest("")), set(_PHOTO_CREDITS))
        self.assertEqual(await suggest("  4 NOT FOUND "), {"404": "404 not found"})
        self.assertEqual(await suggest("teapot"), {"418": "418 i'm a teapot"})
        self.assertEqual(await suggest("202"), {"202": "202 accepted"})
        self.assertEqual(await suggest("999"), {})
        client_errors = await suggest("4")
        self.assertTrue(client_errors)
        self.assertTrue(all(code.startswith("4") for code in client_errors))

    async def test_httpbird_prefix_still_accepts_a_number(self):
        command = self.client.get_command("httpbird")
        ctx = commands.Context(
            message=Mock(content="%httpbird 202", attachments=[]),
            bot=self.client,
            view=StringView(" 202"),
            prefix="%",
            invoked_with="httpbird",
            command=command,
        )
        ctx.reply = AsyncMock()
        await command._parse_arguments(ctx)
        await command.callback(*ctx.args, **ctx.kwargs)
        ctx.reply.assert_awaited_once()
        self.assertEqual(ctx.reply.await_args.args, ("202 accepted",))
        self.assertEqual(ctx.reply.await_args.kwargs["file"].filename, "httpbird-202.jpg")

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
