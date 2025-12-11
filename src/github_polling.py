import asyncio
import logging
from typing import Set
from github import GithubException

from github_api import github_api
from redis_storage import storage
from event_handlers import (
    format_push_event,
    format_issues_event,
    format_issue_comment_event,
    format_pull_request_event,
    format_pr_review_comment_event,
    format_workflow_run_event,
    get_event_type_for_filter,
    get_author_from_event
)

logger = logging.getLogger(__name__)


class GitHubPoller:
    """
    Опрос GitHub API для получения новых событий
    """

    def __init__(self, notification_func=None, poll_interval=60):
        self.notification_func = notification_func
        self.poll_interval = poll_interval  # секунды между проверками
        self.running = False

    async def start(self):
        """Запуск polling"""
        self.running = True
        logger.info(f"GitHub polling started (interval: {self.poll_interval}s)")

        while self.running:
            try:
                await self.poll_all_repos()
            except Exception as e:
                logger.error(f"Error in polling cycle: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """Остановка polling"""
        self.running = False
        logger.info("GitHub polling stopped")

    async def poll_all_repos(self):
        """Опрос всех отслеживаемых репозиториев"""
        # Получаем все уникальные репозитории из всех подписок
        repos = self._get_all_subscribed_repos()

        if not repos:
            logger.debug("No repositories to poll")
            return

        logger.info(f"Polling {len(repos)} repositories...")

        for repo_url in repos:
            try:
                await self.poll_repo(repo_url)
            except Exception as e:
                logger.error(f"Error polling {repo_url}: {e}", exc_info=True)

    def _get_all_subscribed_repos(self) -> Set[str]:
        """Получить все репозитории, на которые есть подписки"""
        repos = set()
        # Это нужно реализовать в storage - получение всех repo_url
        # Пока используем хак через сканирование ключей
        try:
            for key in storage.client.scan_iter("repo_chats:*"):
                repo_url = key.replace("repo_chats:", "")
                repos.add(repo_url)
        except Exception as e:
            logger.error(f"Error getting subscribed repos: {e}")

        return repos

    async def poll_repo(self, repo_url: str):
        """Опрос одного репозитория"""
        parsed = github_api.parse_repo_url(repo_url)
        if not parsed:
            logger.warning(f"Cannot parse repo URL: {repo_url}")
            return

        owner, repo_name = parsed

        try:
            # Получаем репозиторий
            repo = github_api.get_repo(owner, repo_name)
            if not repo:
                logger.warning(f"Repository not found: {repo_url}")
                return

            # Получаем последние события
            events = repo.get_events()

            # Получаем ID последнего обработанного события
            last_event_id = storage.get_last_event_id(repo_url)

            new_events = []
            for event in events:
                if last_event_id and event.id == last_event_id:
                    # Дошли до последнего обработанного события
                    break
                new_events.append(event)

            if not new_events:
                logger.debug(f"No new events for {repo_url}")
                return

            # Обрабатываем события в обратном порядке (от старых к новым)
            new_events.reverse()

            logger.info(f"Found {len(new_events)} new events for {repo_url}")

            for event in new_events:
                await self.process_event(repo_url, event)

            # Сохраняем ID последнего обработанного события
            if new_events:
                storage.set_last_event_id(repo_url, new_events[-1].id)

        except GithubException as e:
            logger.error(f"GitHub API error for {repo_url}: {e}")
        except Exception as e:
            logger.error(f"Error polling {repo_url}: {e}", exc_info=True)

    async def process_event(self, repo_url: str, event):
        """Обработка одного события"""
        event_type = event.type
        payload = event.payload

        # Добавляем информацию о репозитории в payload
        if "repository" not in payload:
            payload["repository"] = {
                "html_url": repo_url,
                "full_name": f"{event.repo.name}"
            }

        # Добавляем sender и actor (для совместимости)
        if event.actor:
            if "sender" not in payload:
                payload["sender"] = {
                    "login": event.actor.login
                }
            if "actor" not in payload:
                payload["actor"] = {
                    "login": event.actor.login
                }

        logger.info(f"Processing event: {event_type} for {repo_url}")
        logger.debug(f"Event payload keys: {list(payload.keys())}")

        # Форматируем событие
        text, event_key = self.format_event(event_type, payload)

        if not text:
            logger.warning(f"⚠️ No handler or empty text for event type: {event_type}")
            return

        logger.info(f"✅ Formatted event text (preview): {text[:100]}...")

        # Получаем подписанные чаты
        chat_ids = storage.get_chats_for_repo(repo_url)

        if not chat_ids:
            logger.warning(f"⚠️ No subscribed chats for {repo_url}")
            return

        logger.info(f"Found {len(chat_ids)} subscribed chats: {chat_ids}")

        # Получаем автора и тип для фильтрации
        author = get_author_from_event(event_type, payload)
        filter_event_type = get_event_type_for_filter(event_type)

        logger.info(f"Event type: {event_type} → filter type: {filter_event_type}, author: {author}")

        # Отправляем уведомления
        for chat_id in chat_ids:
            # Проверяем фильтры
            filters = storage.get_filters(chat_id, repo_url)
            logger.info(f"Filters for chat {chat_id}: {filters}")

            if filters:
                # Проверка типа события
                event_types = filters.get("event_types", [])
                if event_types and filter_event_type not in event_types:
                    logger.info(f"⚠️ Event type {filter_event_type} filtered out for chat {chat_id} (allowed: {event_types})")
                    continue

                # Проверка автора
                excluded_authors = filters.get("excluded_authors", [])
                if author and author in excluded_authors:
                    logger.info(f"⚠️ Author {author} filtered out for chat {chat_id}")
                    continue

            # Отправляем уведомление
            if self.notification_func:
                try:
                    await self.notification_func(
                        chat_id=chat_id,
                        text=text,
                        event_key=event_key,
                        edit_existing=False
                    )
                    logger.info(f"✅ Notification sent to chat {chat_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to send notification to {chat_id}: {e}", exc_info=True)

    def format_event(self, event_type: str, payload: dict) -> tuple[str, str]:
        """Форматирование события в текст сообщения"""
        handlers = {
            "PushEvent": format_push_event,
            "IssuesEvent": format_issues_event,
            "IssueCommentEvent": format_issue_comment_event,
            "PullRequestEvent": format_pull_request_event,
            "PullRequestReviewCommentEvent": format_pr_review_comment_event,
            "WorkflowRunEvent": format_workflow_run_event,
        }

        handler = handlers.get(event_type)
        if not handler:
            return None, None

        try:
            return handler(payload)
        except Exception as e:
            logger.error(f"Error formatting event {event_type}: {e}", exc_info=True)
            return None, None
