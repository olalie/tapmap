"""Task Scheduler 2.0 COM I/O via pythonnet reflection (no comtypes/win32com).

clr and System.* are imported lazily inside functions, not at module load,
so this module stays importable on non-Windows platforms.
"""

from __future__ import annotations

from typing import Any, Final

from .windows_identity import (
    ACTION_TYPE_EXEC,
    TRIGGER_TYPE_LOGON,
    TaskInfo,
    is_recognized_as_ours,
)

TASK_NAME: Final[str] = "TapMap"

_ROOT_FOLDER: Final[str] = "\\"
_LOGON_INTERACTIVE_TOKEN: Final[int] = 3  # TASK_LOGON_INTERACTIVE_TOKEN
_RUNLEVEL_LUA: Final[int] = 0  # TASK_RUNLEVEL_LUA
_CREATE_OR_UPDATE: Final[int] = 6  # TASK_CREATE_OR_UPDATE
_ERROR_FILE_NOT_FOUND_HRESULT: Final[int] = -2147024894  # 0x80070002

_BindingFlags: Any = None
_Missing: Any = None
_Array: Any = None
_Object: Any = None
_Activator: Any = None
_Type: Any = None


class TaskQueryError(Exception):
    """Native Task Scheduler state could not be read or written reliably."""


class TaskOwnershipConflict(Exception):
    """A task exists at TASK_NAME but was not recognized as ours; never written."""


def _ensure_loaded() -> None:
    """Load the pythonnet/.NET reflection surface used for late binding. Idempotent."""
    global _BindingFlags, _Missing, _Array, _Object, _Activator, _Type

    if _BindingFlags is not None:
        return

    import clr

    clr.AddReference("System")
    from System import Activator, Array, Object, Type
    from System.Reflection import BindingFlags, Missing

    _BindingFlags = BindingFlags
    _Missing = Missing
    _Array = Array
    _Object = Object
    _Activator = Activator
    _Type = Type


def _object_array(args: list[Any]) -> Any:
    """Build a .NET object array from a Python list."""
    arr = _Array.CreateInstance(_Object, len(args))
    for i, value in enumerate(args):
        arr[i] = value
    return arr


def _invoke(obj: Any, name: str, *args: Any) -> Any:
    """Call a COM method via reflection."""
    return obj.GetType().InvokeMember(
        name, _BindingFlags.InvokeMethod, None, obj, _object_array(list(args))
    )


def _get(obj: Any, name: str) -> Any:
    """Read a COM property via reflection."""
    return obj.GetType().InvokeMember(
        name, _BindingFlags.GetProperty, None, obj, _object_array([])
    )


def _get_indexed(obj: Any, name: str, index: int) -> Any:
    """Read a COM indexed property (e.g. collection.Item[index]).

    Item is a property getter, not a method - InvokeMethod fails with
    DISP_E_MEMBERNOTFOUND. Use GetProperty instead.
    """
    return obj.GetType().InvokeMember(
        name, _BindingFlags.GetProperty, None, obj, _object_array([index])
    )


def _set(obj: Any, name: str, value: Any) -> None:
    """Set a COM property via reflection."""
    obj.GetType().InvokeMember(
        name, _BindingFlags.SetProperty, None, obj, _object_array([value])
    )


def _connect_service() -> Any:
    """Connect to the Task Scheduler service."""
    service_type = _Type.GetTypeFromProgID("Schedule.Service")
    if service_type is None:
        raise TaskQueryError("Task Scheduler COM class (Schedule.Service) is not registered")
    service = _Activator.CreateInstance(service_type)
    _invoke(service, "Connect")
    return service


def _root_folder(service: Any) -> Any:
    """Return the root task folder."""
    return _invoke(service, "GetFolder", _ROOT_FOLDER)


def _read_task_info(task: Any) -> TaskInfo:
    """Read a task's fields into a TaskInfo."""
    definition = _get(task, "Definition")
    principal = _get(definition, "Principal")
    triggers = _get(definition, "Triggers")
    actions = _get(definition, "Actions")

    trigger_count = int(_get(triggers, "Count"))
    trigger_is_logon = False
    trigger_user_id = None
    if trigger_count == 1:
        trigger = _get_indexed(triggers, "Item", 1)
        trigger_is_logon = int(_get(trigger, "Type")) == TRIGGER_TYPE_LOGON
        if trigger_is_logon:
            trigger_user_id = _get(trigger, "UserId")

    action_count = int(_get(actions, "Count"))
    action_path = None
    action_arguments = None
    if action_count == 1:
        action = _get_indexed(actions, "Item", 1)
        if int(_get(action, "Type")) == ACTION_TYPE_EXEC:
            action_path = _get(action, "Path")
            action_arguments = _get(action, "Arguments")

    return TaskInfo(
        enabled=bool(_get(task, "Enabled")),
        logon_type=int(_get(principal, "LogonType")),
        run_level=int(_get(principal, "RunLevel")),
        trigger_count=trigger_count,
        trigger_is_logon=trigger_is_logon,
        trigger_user_id=trigger_user_id,
        principal_user_id=_get(principal, "UserId"),
        action_count=action_count,
        action_path=action_path,
        action_arguments=action_arguments,
    )


def find_task() -> TaskInfo | None:
    """Return the current "TapMap" task's fields, or None if no such task exists.

    Raises:
        TaskQueryError: Task Scheduler could not be reached or queried reliably.
    """
    _ensure_loaded()
    try:
        service = _connect_service()
        folder = _root_folder(service)
        try:
            task = _invoke(folder, "GetTask", TASK_NAME)
        except Exception as exc:
            if _hresult_of(exc) == _ERROR_FILE_NOT_FOUND_HRESULT:
                return None
            raise TaskQueryError(str(exc)) from exc
        return _read_task_info(task)
    except TaskQueryError:
        raise
    except Exception as exc:
        raise TaskQueryError(str(exc)) from exc


def _hresult_of(exc: Exception) -> int | None:
    """Return the HRESULT of exc, unwrapping InvokeMember's TargetInvocationException."""
    inner = getattr(exc, "InnerException", None)
    target = inner if inner is not None else exc
    hresult = getattr(target, "HResult", None)
    return int(hresult) if hresult is not None else None


def _build_task_definition(service: Any, *, exe_path: str, arguments: str, username: str) -> Any:
    """Build a new task definition."""
    task_def = _invoke(service, "NewTask", 0)

    principal = _get(task_def, "Principal")
    _set(principal, "LogonType", _LOGON_INTERACTIVE_TOKEN)
    _set(principal, "RunLevel", _RUNLEVEL_LUA)
    _set(principal, "UserId", username)

    triggers = _get(task_def, "Triggers")
    trigger = _invoke(triggers, "Create", TRIGGER_TYPE_LOGON)
    _set(trigger, "UserId", username)

    actions = _get(task_def, "Actions")
    action = _invoke(actions, "Create", ACTION_TYPE_EXEC)
    _set(action, "Path", exe_path)
    _set(action, "Arguments", arguments)

    return task_def


def create_or_update_task_if_owned_or_absent(
    *, exe_path: str, arguments: str, username: str
) -> None:
    """Create the canonical task, or update it if still owned, in one COM session.

    Raises:
        TaskQueryError: Task Scheduler could not be reached or queried reliably.
        TaskOwnershipConflict: A task now exists and is not recognized as
            ours; never written.
    """
    _ensure_loaded()
    try:
        service = _connect_service()
        folder = _root_folder(service)

        try:
            existing = _invoke(folder, "GetTask", TASK_NAME)
        except Exception as exc:
            if _hresult_of(exc) != _ERROR_FILE_NOT_FOUND_HRESULT:
                raise TaskQueryError(str(exc)) from exc
            existing = None

        if existing is not None:
            info = _read_task_info(existing)
            if not is_recognized_as_ours(info, current_username=username, exe_path=exe_path):
                raise TaskOwnershipConflict("a task now exists and is not recognized as ours")

        task_def = _build_task_definition(
            service, exe_path=exe_path, arguments=arguments, username=username
        )
        _invoke(
            folder,
            "RegisterTaskDefinition",
            TASK_NAME,
            task_def,
            _CREATE_OR_UPDATE,
            _Missing.Value,
            _Missing.Value,
            _LOGON_INTERACTIVE_TOKEN,
            _Missing.Value,
        )
    except (TaskQueryError, TaskOwnershipConflict):
        raise
    except Exception as exc:
        raise TaskQueryError(str(exc)) from exc


def set_task_enabled_if_recognized(
    enabled: bool, *, current_username: str, exe_path: str
) -> None:
    """Enable or disable the "TapMap" task in the same COM session used to verify it.

    Raises:
        TaskQueryError: Task Scheduler could not be reached, or the task no
            longer exists.
        TaskOwnershipConflict: The task exists but is not recognized as ours;
            never written.
    """
    _ensure_loaded()
    try:
        service = _connect_service()
        folder = _root_folder(service)

        try:
            task = _invoke(folder, "GetTask", TASK_NAME)
        except Exception as exc:
            if _hresult_of(exc) == _ERROR_FILE_NOT_FOUND_HRESULT:
                raise TaskQueryError("TapMap task no longer exists") from exc
            raise TaskQueryError(str(exc)) from exc

        info = _read_task_info(task)
        if not is_recognized_as_ours(info, current_username=current_username, exe_path=exe_path):
            raise TaskOwnershipConflict("existing task is not recognized as ours")

        _set(task, "Enabled", enabled)
    except (TaskQueryError, TaskOwnershipConflict):
        raise
    except Exception as exc:
        raise TaskQueryError(str(exc)) from exc
