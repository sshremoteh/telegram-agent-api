#!/usr/bin/env python3
"""
Interactive Terminal Control Center for Telegram Agent API.
Provides a modern Rich-powered CLI interface for multi-account management, service control, and tools.
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

import account_manager
from auth import run_auth

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
LOG_PATH = BASE_DIR / "server.log"
console = Console()

def clear_screen():
    console.clear()

def print_header():
    title = Text("TELEGRAM AGENT HUB", style="bold cyan")
    subtitle = Text("Multi-Account MTProto & Local MCP Control Center", style="dim white")
    panel = Panel(
        Text.assemble(title, "\n", subtitle, justify="center"),
        box=box.DOUBLE,
        border_style="bright_blue",
        padding=(1, 2)
    )
    console.print(panel)

def get_server_process():
    try:
        res = subprocess.run(["pgrep", "-f", "python.*[ /]server\\.py"], capture_output=True, text=True)
        pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None

def show_service_status():
    pid = get_server_process()
    if pid:
        status_text = Text(f"● RUNNING (PID: {pid})", style="bold green")
    else:
        status_text = Text("○ STOPPED", style="bold red")

    active_acc = account_manager.get_active_account_name() or "None"
    acc_count = len(account_manager.list_accounts())

    table = Table(box=box.ROUNDED, show_header=False, expand=True)
    table.add_column("Key", style="bold bright_black", width=20)
    table.add_column("Value", style="bold white")

    table.add_row("REST API Service:", status_text)
    table.add_row("Active Account:", Text(active_acc, style="bold cyan"))
    table.add_row("Total Accounts:", str(acc_count))
    table.add_row("Loopback URL:", "http://127.0.0.1:8765")
    table.add_row("Web Dashboard:", "http://127.0.0.1:8765/dashboard")

    console.print(Panel(table, title="[bold]System Status[/bold]", border_style="cyan"))

def list_accounts_view():
    accounts = account_manager.list_accounts()
    if not accounts:
        console.print("[yellow]Нет подключенных аккаунтов. Добавьте первый аккаунт через меню.[/yellow]")
        return

    table = Table(title="Подключенные Telegram-аккаунты", box=box.ROUNDED, expand=True)
    table.add_column("Алиас", style="bold cyan")
    table.add_column("Имя", style="white")
    table.add_column("ID", style="dim")
    table.add_column("Username", style="green")
    table.add_column("Телефон", style="magenta")
    table.add_column("Сессия", style="yellow")
    table.add_column("Статус", justify="center")

    for acc in accounts:
        is_active = acc.get("is_active", False)
        status = "[bold green]АКТИВЕН[/bold green]" if is_active else "[dim]В пуле[/dim]"
        has_file = "✓ Есть" if acc.get("has_session_file") else "✗ Нет файла"
        uname = f"@{acc.get('username')}" if acc.get("username") else "-"
        table.add_row(
            acc.get("alias", ""),
            acc.get("first_name", "") or "-",
            str(acc.get("user_id", "")),
            uname,
            acc.get("phone", "") or "-",
            has_file,
            status
        )
    console.print(table)

def add_new_account():
    console.print(Panel("[bold]Добавление нового Telegram-аккаунта[/bold]", style="cyan"))
    alias = Prompt.ask("Введите уникальный алиас для аккаунта (например: work, main, test01)").strip()
    if not alias:
        console.print("[red]Алиас не может быть пустым.[/red]")
        return
    phone = Prompt.ask("Введите номер телефона (+XXXXXXXXXXX) или оставьте пустым для ввода позже").strip() or None
    
    console.print(f"[green]Запуск процесса авторизации для '{alias}'...[/green]")
    try:
        asyncio.run(run_auth(alias=alias, phone_input=phone))
    except Exception as e:
        console.print(f"[red]Ошибка при авторизации: {e}[/red]")
    Prompt.ask("\nНажмите Enter для продолжения...")

def switch_active_account():
    accounts = account_manager.list_accounts()
    if not accounts:
        console.print("[yellow]Нет доступных аккаунтов.[/yellow]")
        return
    list_accounts_view()
    aliases = [a["alias"] for a in accounts]
    choice = Prompt.ask("\nВыберите алиас аккаунта для активации", choices=aliases)
    if account_manager.set_active_account(choice):
        console.print(f"[bold green]Активный аккаунт переключен на '{choice}'![/bold green]")
        # If server is running, restart to re-init
        if get_server_process():
            if Confirm.ask("Перезапустить фоновый сервис для применения изменений?"):
                restart_server()
    else:
        console.print("[red]Ошибка переключения аккаунта.[/red]")
    Prompt.ask("\nНажмите Enter для продолжения...")

def delete_account():
    accounts = account_manager.list_accounts()
    if not accounts:
        console.print("[yellow]Нет доступных аккаунтов.[/yellow]")
        return
    list_accounts_view()
    aliases = [a["alias"] for a in accounts]
    choice = Prompt.ask("\nВыберите алиас аккаунта для удаления", choices=aliases)
    if Confirm.ask(f"[bold red]Вы уверены, что хотите удалить аккаунт '{choice}' и его файл сессии?[/bold red]"):
        if account_manager.remove_account(choice):
            console.print(f"[green]Аккаунт '{choice}' успешно удален.[/green]")
        else:
            console.print("[red]Ошибка при удалении аккаунта.[/red]")
    Prompt.ask("\nНажмите Enter для продолжения...")

def start_server():
    pid = get_server_process()
    if pid:
        console.print(f"[yellow]Сервер уже запущен (PID: {pid}).[/yellow]")
        return
    cmd = f"nohup {BASE_DIR}/.venv/bin/python {BASE_DIR}/server.py > {LOG_PATH} 2>&1 &"
    subprocess.Popen(cmd, shell=True)
    time.sleep(2)
    new_pid = get_server_process()
    if new_pid:
        console.print(f"[bold green]Сервер успешно запущен (PID: {new_pid})![/bold green]")
    else:
        console.print("[bold red]Не удалось запустить сервер. Проверьте server.log.[/bold red]")

def stop_server():
    pid = get_server_process()
    if not pid:
        console.print("[yellow]Сервер не запущен.[/yellow]")
        return
    try:
        os.kill(pid, 15)
    except OSError:
        subprocess.run(["pkill", "-f", "python.*[ /]server\\.py"])
    time.sleep(1)
    console.print("[bold green]Сервер остановлен.[/bold green]")

def restart_server():
    stop_server()
    start_server()

def view_logs():
    if not LOG_PATH.exists():
        console.print("[yellow]Файл логов server.log пока не создан.[/yellow]")
        Prompt.ask("\nНажмите Enter...")
        return
    try:
        res = subprocess.run(["tail", "-n", "35", str(LOG_PATH)], capture_output=True, text=True)
        console.print(Panel(res.stdout, title="[bold]Последние записи server.log[/bold]", border_style="dim"))
    except Exception as e:
        console.print(f"[red]Ошибка чтения логов: {e}[/red]")
    Prompt.ask("\nНажмите Enter...")

def quick_cleanup():
    accounts = account_manager.list_accounts()
    if not accounts:
        console.print("[yellow]Нет аккаунтов для очистки.[/yellow]")
        return
    list_accounts_view()
    aliases = [a["alias"] for a in accounts]
    choice = Prompt.ask("\nВыберите алиас аккаунта для очистки", choices=aliases)
    console.print("[bold yellow]ВНИМАНИЕ: Будут удалены все диалоги (кроме Избранного и Telegram) и заблокированы все боты![/bold yellow]")
    if Confirm.ask(f"Подтверждаете полную очистку аккаунта '{choice}'?"):
        was_running = bool(get_server_process())
        if was_running:
            console.print("[dim]Остановка сервера на время очистки...[/dim]")
            stop_server()
        try:
            cmd = f"{BASE_DIR}/.venv/bin/python {BASE_DIR}/cleanup.py {choice}"
            subprocess.run(cmd, shell=True)
        finally:
            if was_running:
                console.print("[dim]Перезапуск сервера...[/dim]")
                start_server()
    Prompt.ask("\nНажмите Enter для продолжения...")

def main_menu():
    while True:
        clear_screen()
        print_header()
        show_service_status()

        table = Table(box=box.SIMPLE, show_header=False, expand=True)
        table.add_column("Num", style="bold cyan", width=5)
        table.add_column("Action", style="white")

        table.add_row("[1]", "📋 Список всех аккаунтов")
        table.add_row("[2]", "➕ Добавить новый Telegram-аккаунт")
        table.add_row("[3]", "🔄 Переключить активный аккаунт")
        table.add_row("[4]", "🚫 Удалить аккаунт и сессию")
        table.add_row("[5]", "🧹 Очистка аккаунта (удалить диалоги, заблокировать ботов)")
        table.add_row("[6]", "🚀 Запустить фоновый сервис REST API")
        table.add_row("[7]", "⏹️  Остановить фоновый сервис")
        table.add_row("[8]", "🔄 Перезапустить фоновый сервис")
        table.add_row("[9]", "📄 Просмотр логов (server.log)")
        table.add_row("[0]", "🚪 Выход")

        console.print(Panel(table, title="[bold]Главное меню[/bold]", border_style="bright_blue"))
        choice = Prompt.ask("Выберите действие", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])

        if choice == "1":
            clear_screen()
            print_header()
            list_accounts_view()
            Prompt.ask("\nНажмите Enter для возврата...")
        elif choice == "2":
            clear_screen()
            print_header()
            add_new_account()
        elif choice == "3":
            clear_screen()
            print_header()
            switch_active_account()
        elif choice == "4":
            clear_screen()
            print_header()
            delete_account()
        elif choice == "5":
            clear_screen()
            print_header()
            quick_cleanup()
        elif choice == "6":
            start_server()
            time.sleep(1)
        elif choice == "7":
            stop_server()
            time.sleep(1)
        elif choice == "8":
            restart_server()
            time.sleep(1)
        elif choice == "9":
            view_logs()
        elif choice == "0":
            console.print("[cyan]Выход. Сервер продолжает работать в фоне, если был запущен.[/cyan]")
            break

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[dim]Работа меню завершена.[/dim]")
