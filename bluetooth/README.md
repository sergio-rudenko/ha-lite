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

### «The port is not available» и `dun.py` молчит

Значит WinCE **не открыл RFCOMM** до нетбука. Список модемов уже правильный; ломается порядок.

1. На нетбуке: `sudo python3 bluetooth/dun.py` (должны быть строки `trusted:` и `Жду RFCOMM`).
2. На навигаторе оставьте **одну** пару с ha217b, лишние устройства удалите.
3. **Сначала** Bluetooth manager → ha217b → Dial-up Networking → **Connect**  
   В окне `dun.py` должна появиться строка `★ входящий RFCOMM`.
4. **Потом** Remote Networking → **Bluetooth DUN modem** или **Bluetooth DUN on COM8** → `*99#`.
5. Никогда: Hayes on COM1.

Если на шаге 3 в `dun.py` по-прежнему тихо — пришлите скрин сервисов Bluetooth у ha217b и полный старт `dun.py`.

## Клавиатура WinCE (если снова понадобится PIN)

- ткнуть в поле PIN;
- иконка клавиатуры в трее;
- `ToggleInputPanel.exe`.
