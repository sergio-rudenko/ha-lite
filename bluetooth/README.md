# Bluetooth: S570HD ↔ ha217b

## 1. Сопряжение (PIN 1234)

На нетбуке:

```bash
sudo pkill bt-agent 2>/dev/null || true
sudo bash bluetooth/pair.sh
# по умолчанию PIN 1234
```

На навигаторе: найти **ha217b** → ввести PIN **1234** (экранная клавиатура WinCE).

Без PIN: `sudo bash bluetooth/pair.sh --just-works`.

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

### S570HD: в Bluetooth manager только trusted / untrusted

Сервисов и кнопки Connect к DUN на этой прошивке нет — так и должно быть.

1. В **trusted** только навигатор (`GPS system`). Лишние пары удалите.
2. На нетбуке: `sudo python3 bluetooth/dun.py`.
3. `br-connection-profile-unavailable` при попытке Connect *к* навигатору — норма: он сам клиент, не сервер.
4. Remote Networking → **Bluetooth DUN modem** или **DUN on COM8** → `*99#`.
5. Не Hayes on COM1. Успех = `★ входящий RFCOMM` в `dun.py`.

Если при наборе по-прежнему «port is not available» и нет `★ входящий RFCOMM` — стек WinCE не открывает RFCOMM; пришлите полный старт `dun.py` и список trusted.

## Клавиатура WinCE (если снова понадобится PIN)

- ткнуть в поле PIN;
- иконка клавиатуры в трее;
- `ToggleInputPanel.exe`.
