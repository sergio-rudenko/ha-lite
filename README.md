# ha-lite

Панель Home Assistant для навигатора **S570HD** (Windows CE 5, экран 800×480, только Bluetooth).

Нетбук с Home Assistant (`ha217b`) объявляет Bluetooth-модем. Навигатор дозванивается по DUN и открывает страницу панели.

## Клонирование (GitHub)

```bash
git clone https://github.com/sergio-rudenko/ha-lite.git
cd ha-lite
```

## Сопряжение

На нетбуке:

```bash
sudo bash bluetooth/pair.sh
```

На навигаторе выберите **ha217b** (режим Just Works, без PIN).

## Дозвон

На нетбуке в двух окнах:

```bash
sudo apt-get install -y bluez python3-dbus python3-gi ppp
python3 bluetooth/check_page.py
```

```bash
sudo python3 bluetooth/dun.py
```

На навигаторе: **Make New Connection** → **ha217b** → Dial-Up → номер `*99#` → браузер `http://10.44.0.1:4731/`.
