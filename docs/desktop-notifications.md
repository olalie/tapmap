# Desktop Notifications

TapMap can show desktop notifications for new Significant Connections on Windows, Linux, and macOS.

Desktop notifications are enabled by default. Use **Notifications (N)** in the **INSIGHTS** menu to turn them on or off.

The setting is stored between TapMap sessions.

## Notification behavior

Desktop notifications are separate from Significant Connections history and MQTT notifications.

By default, notifications start after 7 active Insights days. Set `TAPMAP_NOTIFICATION_LEARNING_DAYS` to a value from `0` to `30` to change the learning period. A value of `0` enables notifications immediately.

A desktop notification shows:

- Significance reason
- Application name
- Country

The notification alerts you to a new Significant Connection. Open TapMap and view **Significant Connections** to inspect the event and its details.

Desktop notifications are not available when running TapMap in Docker. MQTT can be used for notifications in Docker.

## Windows

TapMap uses the Windows notification system. Notifications appear under TapMap in Windows notifications.

## macOS

TapMap uses the macOS notification system.

The first time TapMap requests notification permission, macOS asks you to allow notifications.

If you miss or dismiss this request, open **System Settings → Notifications → TapMap** and enable **Allow Notifications**.

After permission is granted, use **Notifications (N)** in TapMap to turn desktop notifications on or off.

## Linux

TapMap uses the desktop notification system provided by Linux.

Notification appearance and history depend on the desktop environment.
