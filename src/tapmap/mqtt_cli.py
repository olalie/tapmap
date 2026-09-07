"""Interactive `tapmap --configure-mqtt` command.

Single entry point for creating, updating, and removing the MQTT
configuration. Never accepts credentials as command-line arguments - the
password is always read through an interactive, non-echoing prompt.
"""

from __future__ import annotations

import getpass
from collections.abc import Callable
from typing import TYPE_CHECKING

from .mqtt_config import (
    MqttConfig,
    clear_credentials,
    delete_mqtt_config,
    get_stored_credentials,
    load_mqtt_config,
    mqtt_config_path,
    save_mqtt_config,
    set_credentials,
)

if TYPE_CHECKING:
    from .runtime import RuntimeContext

DEFAULT_TOPIC = "tapmap/significant_connections"
DEFAULT_PORT_PLAIN = 1883
DEFAULT_PORT_TLS = 8883


def run_configure_mqtt(
    runtime: RuntimeContext,
    *,
    prompt: Callable[[str], str] = input,
    prompt_secret: Callable[[str], str] = getpass.getpass,
    output: Callable[[str], None] = print,
) -> int:
    """Run the interactive MQTT configuration flow. Returns a process exit code."""
    path = mqtt_config_path(runtime.app_data_dir)
    existing = load_mqtt_config(path)

    if existing is not None:
        output(
            "MQTT is currently configured: "
            f"host={existing.host}, port={existing.port}, "
            f"topic={existing.topic}, tls={'on' if existing.tls else 'off'}"
        )
        if _prompt_yes_no(prompt, output, "Disable MQTT instead of reconfiguring?", default=False):
            delete_mqtt_config(path)
            if not runtime.is_docker:
                clear_credentials()
            output("MQTT disabled.")
            return 0

    host = _prompt_required(prompt, output, "Host", default=existing.host if existing else None)
    tls = _prompt_yes_no(prompt, output, "Use TLS?", default=existing.tls if existing else False)
    port = _prompt_port(prompt, output, default=_derive_default_port(existing, tls))
    topic = _prompt_required(
        prompt, output, "Topic", default=existing.topic if existing else DEFAULT_TOPIC
    )

    username, password, use_auth, deferred_credential_action = _prompt_credentials(
        prompt, prompt_secret, output, runtime=runtime, existing=existing
    )

    if (
        use_auth
        and not tls
        and not _prompt_yes_no(
            prompt,
            output,
            "Username/password without TLS sends credentials in plaintext "
            "over the network. Continue?",
            default=False,
        )
    ):
        output("Not saved.")
        return 0

    config = MqttConfig(
        host=host, port=port, topic=topic, tls=tls, username=username, password=password
    )

    try:
        save_mqtt_config(path, config)
    except OSError as exc:
        output(f"Unable to save MQTT configuration: {exc}")
        return 1

    # Only mutate the keyring once the configuration itself is confirmed
    # saved, so a failed save never leaves credentials changed on their own.
    if deferred_credential_action is not None:
        deferred_credential_action()

    output(
        f"MQTT configuration saved: host={host}, port={port}, "
        f"topic={topic}, tls={'on' if tls else 'off'}"
    )
    return 0


def _prompt_credentials(
    prompt: Callable[[str], str],
    prompt_secret: Callable[[str], str],
    output: Callable[[str], None],
    *,
    runtime: RuntimeContext,
    existing: MqttConfig | None,
) -> tuple[str | None, str | None, bool, Callable[[], None] | None]:
    """Run the auth yes/no gate and, if enabled, the keep/replace/collect flow.

    Returns (username, password, use_auth, deferred_credential_action).
    username/password are the values to embed in the saved MqttConfig -
    always (None, None) on desktop, since desktop credentials live in the
    OS keyring instead. deferred_credential_action, when not None, is the
    keyring mutation (set or clear) the caller must run only after the
    configuration has actually been saved - this function itself never
    touches the keyring, so a failed or declined save leaves it untouched.
    """
    if runtime.is_docker:
        existing_username = existing.username if existing else None
        existing_password = existing.password if existing else None
    else:
        existing_username, existing_password = get_stored_credentials()

    has_existing = bool(existing_username)

    use_auth = _prompt_yes_no(
        prompt,
        output,
        "Use username/password authentication?"
        + (" (currently configured)" if has_existing else ""),
        default=has_existing,
    )

    if not use_auth:
        if has_existing and not runtime.is_docker:
            return None, None, False, clear_credentials
        return None, None, False, None

    if has_existing and _prompt_yes_no(prompt, output, "Keep existing credentials?", default=True):
        if runtime.is_docker:
            return existing_username, existing_password, True, None
        return None, None, True, None

    username = _prompt_required(prompt, output, "Username")
    output("Input is hidden - nothing will appear as you type.")
    entered_password = prompt_secret("Password (leave empty for none): ").strip()
    password = entered_password or None

    if runtime.is_docker:
        return username, password, True, None

    return None, None, True, lambda: set_credentials(username, password)


def _derive_default_port(existing: MqttConfig | None, tls: bool) -> int:
    """Return the port to propose as the default for the given TLS answer.

    Fresh setup: the standard port for tls (1883/8883). Reconfiguring:
    the existing port is preserved, unless it exactly matches the standard
    port for the *previous* TLS setting and TLS has just changed - in that
    case the existing port was almost certainly never customized, so the
    standard port for the new TLS setting is proposed instead. A genuinely
    custom port (one that doesn't match the old standard) is always kept.
    """
    if existing is None:
        return DEFAULT_PORT_TLS if tls else DEFAULT_PORT_PLAIN

    existing_standard_port = DEFAULT_PORT_TLS if existing.tls else DEFAULT_PORT_PLAIN
    if tls != existing.tls and existing.port == existing_standard_port:
        return DEFAULT_PORT_TLS if tls else DEFAULT_PORT_PLAIN

    return existing.port


def _prompt_yes_no(
    prompt: Callable[[str], str],
    output: Callable[[str], None],
    question: str,
    *,
    default: bool,
) -> bool:
    """Prompt a yes/no question; blank input accepts the default."""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = prompt(f"{question} {suffix} ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        output("Please answer y or n.")


def _prompt_required(
    prompt: Callable[[str], str],
    output: Callable[[str], None],
    label: str,
    *,
    default: str | None = None,
) -> str:
    """Prompt for required, non-empty text; blank input accepts the default, if any."""
    suffix = f" [{default}]" if default else ""
    while True:
        answer = prompt(f"{label}{suffix}: ").strip()
        if answer:
            return answer
        if default:
            return default
        output(f"{label} is required.")


def _prompt_port(
    prompt: Callable[[str], str],
    output: Callable[[str], None],
    *,
    default: int,
) -> int:
    """Prompt for a TCP port (1-65535); blank input accepts the default."""
    while True:
        answer = prompt(f"Port [{default}]: ").strip()
        if not answer:
            return default
        try:
            port = int(answer)
        except ValueError:
            output("Port must be a number.")
            continue
        if 1 <= port <= 65535:
            return port
        output("Port must be between 1 and 65535.")
