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

1. В **trusted** только **ha217b**. Остальные пары удалите (из‑за них COM8 часто «port is not available»).
2. На нетбуке: `sudo python3 bluetooth/dun.py` — в логе `trusted:`, `connect:` / `link ok:`, затем `Жду RFCOMM`.
3. Remote Networking → **Bluetooth DUN modem** или **Bluetooth DUN on COM8** → номер `*99#`.
4. Не Hayes on COM1.
5. Когда канал реально откроется, в `dun.py` будет `★ входящий RFCOMM`.

Если после `link ok:` всё ещё «port is not available» — пришлите полный вывод старта `dun.py` и точное имя выбранного модема.

## Клавиатура WinCE (если снова понадобится PIN)

- ткнуть в поле PIN;
- иконка клавиатуры в трее;
- `ToggleInputPanel.exe`.
