import re
from typing import Optional, Tuple
from github import Github, GithubException

from config import Config


class GitHubAPI:
    def __init__(self):
        self.client = Github(Config.GITHUB_TOKEN)

    @staticmethod
    def parse_repo_url(url: str) -> Optional[Tuple[str, str]]:
        """
        Парсинг информации через URL репозитория. возвращает (owner, repo)
        """

        patterns = [
            r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
            r"^([^/]+)/([^/]+)$"
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        return None

    def get_repo(self, owner: str, repo_name: str):
        """
        Получить репозиторий
        """

        try:
            return self.client.get_repo(f"{owner}/{repo_name}")
        except GithubException:
            return None

    def create_webhook(self, owner: str, repo_name: str) -> Optional[int]:
        """
        Создать webhook для репозитория
        """

        repo = self.get_repo(owner, repo_name)
        if not repo:
            return None

        webhook_url = Config.get_webhook_url()

        try:
            # проверяем, нет ли существующего webhook
            for hook in repo.get_hooks():
                if hook.config.get("url") == webhook_url:
                    return hook.id

            # создаём новый вебхук
            hook = repo.create_hook(
                name="web",
                config={
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": Config.WEBHOOK_SECRET
                },
                events=["push", "issues", "issue_comment", "pull_request",
                        "pull_request_review_comment", "workflow_run"],
                active=True
            )
            return hook.id
        except GithubException as e:
            print(f"Ошибка создания webhook: {e}")
            return None

    def delete_webhook(self, owner: str, repo_name: str, webhook_id: int) -> bool:
        """
        Удаление webhook
        """

        repo = self.get_repo(owner, repo_name)
        if not repo:
            return False

        try:
            hook = repo.get_hook(webhook_id)
            hook.delete()
            return True
        except GithubException:
            return False

    def get_repo_info(self, owner: str, repo_name: str) -> Optional[dict]:
        """
        Получить информацию о репозитории
        """

        repo = self.get_repo(owner, repo_name)
        if not repo:
            return None

        return {
            "full_name": repo.full_name,
            "description": repo.description,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "private": repo.private
        }


github_api = GitHubAPI()
