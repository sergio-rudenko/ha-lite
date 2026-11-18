# Bluetooth: S570HD ↔ ha217b

## 1. Сопряжение — уже сделано

`ha217b` в trusted на навигаторе.

## 2. Дозвон (сейчас)

На нетбуке в двух окнах:

```bash
# окно 1 — страница проверки
python3 bluetooth/check_page.py

# окно 2 — модем для навигатора
sudo apt-get install -y bluez python3-dbus python3-gi ppp
sudo python3 bluetooth/dun.py
```

На навигаторе:

1. Панель управления → **Make New Connection**
2. Тип: Dial-Up
3. В списке модемов выбрать **Bluetooth / ha217b / Dial-up Networking**
4. Номер **`*99#`**, имя и пароль пустые
5. Подключить
6. Браузер → `http://10.44.0.1:4731/`

### «The port is not available»

Почти всегда выбран не тот модем.

- **Нельзя:** `Hayes compatible on COM1` (или COM2/COM3 без Bluetooth) — порта нет, WinCE так и пишет.
- **Нужно:** модем с именем Bluetooth / ha217b / Dial-up Networking.
- Если такого пункта нет: Bluetooth manager → устройство **ha217b** → сервисы → включить **Dial-up Networking** и/или **Serial Port**. Иногда там же назначают исходящий COM (часто COM6 или COM8) — в Make New Connection выбирайте **этот** COM.
- На нетбуке в момент дозвона должен крутиться `sudo python3 bluetooth/dun.py`. Без него сервисов модема нет.
- После смены службы на нетбуке: на навигаторе отключить/подключить Bluetooth или удалить соединение и создать заново.

Если снова ошибка — пришлите: (1) точный текст, (2) что выбрано в списке модемов, (3) вывод `dun.py`.

## Клавиатура WinCE (если снова понадобится PIN)

- ткнуть в поле PIN;
- иконка клавиатуры в трее;
- `ToggleInputPanel.exe`.
