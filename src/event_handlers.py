from typing import Optional


def format_push_event(payload: dict) -> tuple[str, str]:
    """Форматирование события push"""
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    ref = payload.get("ref", "").replace("refs/heads/", "")
    commits = payload.get("commits", [])

    # Безопасное получение pusher/sender
    pusher = None
    if "pusher" in payload and payload["pusher"]:
        pusher = payload["pusher"].get("name") or payload["pusher"].get("login")
    if not pusher and "sender" in payload and payload["sender"]:
        pusher = payload["sender"].get("login")
    if not pusher and "actor" in payload and payload["actor"]:
        pusher = payload["actor"].get("login")
    pusher = pusher or "Unknown"

    compare_url = payload.get("compare", "")

    text = f"<b>Push в {repo_name}</b>\n"
    text += f"Ветка: <code>{ref}</code>\n"
    text += f"Автор: {pusher}\n\n"

    if commits:
        text += f"<b>Коммиты ({len(commits)}):</b>\n"
        for commit in commits[:10]:  # выводим 10 коммитов
            sha = commit.get("id", "")[:7]
            message = commit.get("message", "").split("\n")[0][:100]
            author = commit.get("author", {}).get("name", "Unknown")
            text += f"<code>{sha}</code> {message}\n"
            text += f"{author}\n"

        if len(commits) > 10:
            text += f"\n... и ещё {len(commits) - 10} коммитов\n"

    if compare_url:
        text += f"\n<a href='{compare_url}'>Сравнить изменения</a>"

    # event_key для редактирования сообщений
    event_key = f"push:{repo_name}:{ref}"

    return text, event_key


def format_issues_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование события issues
    """

    action = payload.get("action", "unknown")
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")

    # Безопасное получение sender
    sender = None
    if "sender" in payload and payload["sender"]:
        sender = payload["sender"].get("login")
    if not sender and "actor" in payload and payload["actor"]:
        sender = payload["actor"].get("login")
    sender = sender or "Unknown"

    issue_number = issue.get("number", 0)
    issue_title = issue.get("title", "No title")
    issue_url = issue.get("html_url", "")
    issue_body = issue.get("body", "") or ""

    actions_map = {
        "opened": "Открыт новый issue",
        "closed": "Issue закрыт",
        "reopened": "Issue открыт заново",
        "edited": "Issue отредактирован"
    }

    action_text = actions_map.get(action, f"Issue: {action}")

    text = f"{action_text}\n"
    text += f"<b>{repo_name}</b>\n\n"
    text += f"<b>#{issue_number}: {issue_title}</b>\n"
    text += f"{sender}\n\n"

    if issue_body and action == "opened":
        body_preview = issue_body[:500]
        if len(issue_body) > 500:
            body_preview += "..."
        text += f"<blockquote>{body_preview}</blockquote>\n"

    if issue_url:
        text += f"\n<a href='{issue_url}'>Открыть issue</a>"

    event_key = f"issue:{repo_name}:{issue_number}"

    return text, event_key


def format_issue_comment_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование комментариев к issue
    """

    action = payload.get("action")
    if action != "created":
        return None, None

    issue = payload.get("issue", {})
    comment = payload.get("comment", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    sender = payload.get("sender", {}).get("login", "Unknown")

    issue_number = issue.get("number")
    issue_title = issue.get("title", "")
    comment_body = comment.get("body", "") or ""
    comment_url = comment.get("html_url", "")

    text = f"<b>Новый комментарий</b>\n"
    text += f"{repo_name}\n\n"
    text += f"<b>#{issue_number}: {issue_title}</b>\n"
    text += f"{sender}\n\n"

    if comment_body:
        body_preview = comment_body[:500]
        if len(comment_body) > 500:
            body_preview += "..."
        text += f"<blockquote>{body_preview}</blockquote>\n"

    text += f"\n<a href='{comment_url}'>Открыть комментарий</a>"

    event_key = f"issue_comment:{repo_name}:{comment.get('id')}"

    return text, event_key


def format_pull_request_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование для pull request
    """

    action = payload.get("action")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    sender = payload.get("sender", {}).get("login", "Unknown")

    pr_number = pr.get("number")
    pr_title = pr.get("title", "")
    pr_url = pr.get("html_url", "")
    pr_body = pr.get("body", "") or ""
    base_branch = pr.get("base", {}).get("ref", "")
    head_branch = pr.get("head", {}).get("ref", "")

    actions_map = {
        "opened": "Создан новый PR",
        "closed": "PR закрыт" if not pr.get("merged") else "Выполнен merge",
        "reopened": "PR открыт заново",
        "edited": "PR отредактирован",
        "review_requested": "Запрошен review",
        "synchronize": "PR обновлён"
    }

    action_text = actions_map.get(action, f"PR: {action}")

    text = f"{action_text}\n"
    text += f"<b>{repo_name}</b>\n\n"
    text += f"<b>#{pr_number}: {pr_title}</b>\n"
    text += f"{sender}\n"
    text += f"{head_branch} → {base_branch}\n\n"

    if pr_body and action == "opened":
        body_preview = pr_body[:500]
        if len(pr_body) > 500:
            body_preview += "..."
        text += f"<blockquote>{body_preview}</blockquote>\n"

    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    changed_files = pr.get("changed_files", 0)
    text += f"\n+{additions} / -{deletions} |  {changed_files} файлов\n"

    text += f"\n<a href='{pr_url}'>Открыть Pull Request</a>"

    event_key = f"pr:{repo_name}:{pr_number}"

    return text, event_key


def format_pr_review_comment_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование комментария к обзору на Pull Request
    """

    action = payload.get("action")
    if action != "created":
        return None, None

    pr = payload.get("pull_request", {})
    comment = payload.get("comment", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    sender = payload.get("sender", {}).get("login", "Unknown")

    pr_number = pr.get("number")
    pr_title = pr.get("title", "")
    comment_body = comment.get("body", "") or ""
    comment_url = comment.get("html_url", "")
    path = comment.get("path", "")

    text = f"<b>Комментарий к коду в PR</b>\n"
    text += f"{repo_name}\n\n"
    text += f"<b>#{pr_number}: {pr_title}</b>\n"
    text += f"{sender}\n"
    text += f"{path}\n\n"

    if comment_body:
        body_preview = comment_body[:500]
        if len(comment_body) > 500:
            body_preview += "..."
        text += f"<blockquote>{body_preview}</blockquote>\n"

    text += f"\n<a href='{comment_url}'>Открыть комментарий</a>"

    event_key = f"pr_comment:{repo_name}:{comment.get('id')}"

    return text, event_key


def format_workflow_run_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование события GitHub Actions
    """

    action = payload.get("action")
    workflow_run = payload.get("workflow_run", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")

    workflow_name = workflow_run.get("name", "Unknown workflow")
    status = workflow_run.get("status", "")
    conclusion = workflow_run.get("conclusion", "")
    run_url = workflow_run.get("html_url", "")
    branch = workflow_run.get("head_branch", "")
    actor = workflow_run.get("actor", {}).get("login", "Unknown")
    run_number = workflow_run.get("run_number", "")

    status_map = {
        "success": "Успешно",
        "failure": "Ошибка",
        "cancelled": "Отменён",
        "skipped": "Пропущен",
        "in_progress": "Выполняется",
        "queued": "В очереди"
    }

    if action == "completed":
        status_text = status_map.get(conclusion, conclusion)
    else:
        status_text = status_map.get(status, status)

    text = f"⚙<b>GitHub Actions</b>\n"
    text += f"{repo_name}\n\n"
    text += f"<b>{workflow_name}</b> #{run_number}\n"
    text += f"Ветка: {branch}\n"
    text += f"{actor}\n\n"
    text += f"Статус: {status_text}\n"

    text += f"\n<a href='{run_url}'>Открыть workflow</a>"

    event_key = f"workflow:{repo_name}:{workflow_run.get('id')}"

    return text, event_key


def get_event_handler(event_type: str):
    """
    Получить информацию об обработчике по типу события
    """

    handlers = {
        "push": format_push_event,
        "issues": format_issues_event,
        "issue_comment": format_issue_comment_event,
        "pull_request": format_pull_request_event,
        "pull_request_review_comment": format_pr_review_comment_event,
        "workflow_run": format_workflow_run_event
    }
    return handlers.get(event_type)


def get_author_from_event(event_type: str, payload: dict) -> Optional[str]:
    """
    Получить автора события
    Поддерживает как webhook события, так и Events API
    """

    # Для push событий
    if event_type in ("push", "PushEvent"):
        # Webhook
        pusher = payload.get("pusher", {})
        if pusher:
            return pusher.get("name") or pusher.get("login")
        # Events API может использовать другую структуру
        return payload.get("sender", {}).get("login")

    # Для остальных событий - берём sender.login
    sender = payload.get("sender", {})
    if sender:
        return sender.get("login")

    # Fallback - может быть в других полях
    return payload.get("actor", {}).get("login")


def get_event_type_for_filter(event_type: str) -> str:
    """
    Преобразовать тип события GitHub в тип для фильтра
    Поддерживает как webhook события, так и Events API
    """

    mapping = {
        # Webhook event types
        "push": "push",
        "issues": "issues",
        "issue_comment": "issues",
        "pull_request": "pull_request",
        "pull_request_review_comment": "pull_request",
        "workflow_run": "workflow_run",

        # Events API event types
        "PushEvent": "push",
        "IssuesEvent": "issues",
        "IssueCommentEvent": "issues",
        "PullRequestEvent": "pull_request",
        "PullRequestReviewEvent": "pull_request",
        "PullRequestReviewCommentEvent": "pull_request",
        "WorkflowRunEvent": "workflow_run",
        "CreateEvent": "push",  # Создание ветки/тега
        "DeleteEvent": "push",  # Удаление ветки/тега
    }
    return mapping.get(event_type, event_type)
