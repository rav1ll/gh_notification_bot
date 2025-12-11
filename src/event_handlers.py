from typing import Optional
import html


def format_push_event(payload: dict) -> tuple[str, str]:
    """Форматирование события push"""
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    ref = payload.get("ref", "").replace("refs/heads/", "")
    commits = payload.get("commits", [])

    # GitHub Events API может не возвращать commits, используем size
    if not commits:
        size = payload.get("size", 0)
        commits = []  # Будем показывать количество, но не детали

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

    # Формируем ссылку на ветку
    repo_html_url = repo.get("html_url", "")
    branch_url = f"{repo_html_url}/tree/{ref}" if repo_html_url else ""

    text = f"📤 <b>Push в {html.escape(repo_name)}</b>\n"
    if branch_url:
        text += f'Ветка: <a href="{html.escape(branch_url)}">{html.escape(ref)}</a>\n'
    else:
        text += f"Ветка: <code>{html.escape(ref)}</code>\n"
    text += f"Автор: {html.escape(pusher)}\n\n"

    commit_count = payload.get("size", len(commits))

    if commits:
        text += f"<b>Коммиты ({len(commits)}):</b>\n"
        for commit in commits[:10]:  # выводим 10 коммитов
            sha = commit.get("id", "")[:7]
            message = commit.get("message", "").split("\n")[0][:100]
            author = commit.get("author", {}).get("name", "Unknown")
            text += f"<code>{html.escape(sha)}</code> {html.escape(message)}\n"
            text += f"{html.escape(author)}\n"

        if len(commits) > 10:
            text += f"\n... и ещё {len(commits) - 10} коммитов\n"
    elif commit_count > 0:
        # Если commits не переданы, но есть size
        text += f"{commit_count} коммит(ов)\n"

    if compare_url:
        text += f'\n<a href="{compare_url}">Сравнить изменения</a>'

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

    action_text = actions_map.get(action, f"Issue: {html.escape(action)}")

    text = f"{action_text}\n"
    text += f"<b>{html.escape(repo_name)}</b>\n"
    text += f"<b>#{issue_number}: {html.escape(issue_title)}</b>\n"
    text += f"{html.escape(sender)}"

    if issue_body and action == "opened":
        body_preview = issue_body[:500]
        if len(issue_body) > 500:
            body_preview += "..."
        text += f"\n\n<blockquote>{html.escape(body_preview)}</blockquote>"

    if issue_url:
        text += f'\n<a href="{html.escape(issue_url)}">Открыть issue</a>'

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
    text += f"{html.escape(repo_name)}\n"
    text += f"<b>#{issue_number}: {html.escape(issue_title)}</b>\n"
    text += f"{html.escape(sender)}"

    if comment_body:
        body_preview = comment_body[:500]
        if len(comment_body) > 500:
            body_preview += "..."
        text += f"\n\n<blockquote>{html.escape(body_preview)}</blockquote>"

    if comment_url:
        text += f'\n<a href="{html.escape(comment_url)}">Открыть комментарий</a>'

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
    pr_title = pr.get("title", "") or "Без названия"
    pr_url = pr.get("html_url", "")
    pr_body = pr.get("body", "") or ""
    base_branch = pr.get("base", {}).get("ref", "unknown")
    head_branch = pr.get("head", {}).get("ref", "unknown")

    actions_map = {
        "opened": "Создан новый PR",
        "closed": "PR закрыт" if not pr.get("merged") else "Выполнен merge",
        "reopened": "PR открыт заново",
        "edited": "PR отредактирован",
        "review_requested": "Запрошен review",
        "synchronize": "PR обновлён"
    }

    action_text = actions_map.get(action, f"PR: {html.escape(action)}")

    text = f"{action_text}\n"
    text += f"<b>{html.escape(repo_name)}</b>\n"
    text += f"<b>#{pr_number}: {html.escape(pr_title)}</b>\n"
    text += f"{html.escape(sender)}\n"
    text += f"{html.escape(head_branch)} → {html.escape(base_branch)}"

    if pr_body and action == "opened":
        body_preview = pr_body[:500]
        if len(pr_body) > 500:
            body_preview += "..."
        text += f"\n\n<blockquote>{html.escape(body_preview)}</blockquote>"

    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    changed_files = pr.get("changed_files", 0)
    text += f"\n+{additions} / -{deletions} | {changed_files} файлов"

    # Добавляем ссылку на PR, если доступна
    if pr_url:
        text += f'\n<a href="{html.escape(pr_url)}">Открыть Pull Request</a>'

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
    pr_title = pr.get("title", "") or "Без названия"
    comment_body = comment.get("body", "") or ""
    comment_url = comment.get("html_url", "")
    path = comment.get("path", "unknown file")

    text = f"<b>Комментарий к коду в PR</b>\n"
    text += f"{html.escape(repo_name)}\n"
    text += f"<b>#{pr_number}: {html.escape(pr_title)}</b>\n"
    text += f"{html.escape(sender)}\n"
    text += f"{html.escape(path)}"

    if comment_body:
        body_preview = comment_body[:500]
        if len(comment_body) > 500:
            body_preview += "..."
        text += f"\n\n<blockquote>{html.escape(body_preview)}</blockquote>"

    if comment_url:
        text += f'\n<a href="{html.escape(comment_url)}">Открыть комментарий</a>'

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
        status_text = status_map.get(conclusion, html.escape(conclusion))
    else:
        status_text = status_map.get(status, html.escape(status))

    text = f"⚙<b>GitHub Actions</b>\n"
    text += f"{html.escape(repo_name)}\n"
    text += f"<b>{html.escape(workflow_name)}</b> #{run_number}\n"
    text += f"Ветка: {html.escape(branch)}\n"
    text += f"{html.escape(actor)}\n"
    text += f"Статус: {status_text}"

    if run_url:
        text += f'\n<a href="{html.escape(run_url)}">Открыть workflow</a>'

    event_key = f"workflow:{repo_name}:{workflow_run.get('id')}"

    return text, event_key


def format_create_event(payload: dict) -> tuple[str, str]:
    """
    Форматирование события создания ветки/тега
    """

    ref_type = payload.get("ref_type", "unknown")
    ref = payload.get("ref", "unknown")
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "Unknown")
    repo_html_url = repo.get("html_url", "")

    # Безопасное получение sender
    sender = None
    if "sender" in payload and payload["sender"]:
        sender = payload["sender"].get("login")
    if not sender and "actor" in payload and payload["actor"]:
        sender = payload["actor"].get("login")
    sender = sender or "Unknown"

    if ref_type == "branch":
        emoji = "➕"
        type_text = "Создана новая ветка"
        ref_url = f"{repo_html_url}/tree/{ref}" if repo_html_url else ""
    elif ref_type == "tag":
        emoji = "➕"
        type_text = "Создан новый тег"
        ref_url = f"{repo_html_url}/releases/tag/{ref}" if repo_html_url else ""
    else:
        emoji = "➕"
        type_text = f"Создан {ref_type}"
        ref_url = ""

    text = f"{emoji} <b>{type_text}</b>\n"
    text += f"<b>{html.escape(repo_name)}</b>\n"

    if ref_url:
        text += f'<a href="{html.escape(ref_url)}">{html.escape(ref)}</a>\n'
    else:
        text += f"<code>{html.escape(ref)}</code>\n"

    text += f"{html.escape(sender)}"

    event_key = f"create:{repo_name}:{ref}"

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
        "workflow_run": format_workflow_run_event,
        "CreateEvent": format_create_event
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
