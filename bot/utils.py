from decimal import Decimal, InvalidOperation, ROUND_DOWN


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def ask_choice(prompt: str, choices: dict[str, str]) -> str | None:
    print(prompt)
    for key, label in choices.items():
        print(f"  {key}. {label}")
    selected = input("Choose: ").strip()
    if selected not in choices:
        print("Invalid choice.")
        return None
    return selected


def to_decimal(value: str, label: str = "value") -> Decimal | None:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        print(f"Invalid {label}.")
        return None
    if number <= 0:
        print(f"{label} must be greater than zero.")
        return None
    return number


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def confirm(message: str, require_yes: bool = False) -> bool:
    if require_yes:
        answer = input(f"{message} Type yes to confirm: ").strip().lower()
        if answer in {"yes", "y"}:
            return True
        print("Not confirmed (type yes). Order was NOT sent to Bybit.")
        return False
    answer = input(f"{message} (y/n): ").strip().lower()
    return answer in {"y", "yes"}


def print_kv(data: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        print(f"{key}: {data.get(key, 'N/A')}")
