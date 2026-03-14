# TapMap

![TapMap demo](docs/images/demo.gif)

**See where your computer connects on a live world map.**

TapMap inspects local socket data, enriches IP addresses with geolocation, and visualizes the locations on an interactive map.

It uses:

- `psutil` to read active network connections  
- MaxMind GeoLite2 databases for IP geolocation  
- Dash and Plotly to render an interactive world map  

Architecture: local socket scan → IP extraction → GeoIP lookup → map rendering.

TapMap runs entirely on your own machine.  
It is not a firewall or a full security suite.  
It makes network activity visible on a world map and easy to inspect with hover and click.

---

## Documentation

README and API reference:

https://olalie.github.io/tapmap/

---

## Download

Download the latest version from the  
[Releases page](https://github.com/olalie/tapmap/releases)

Available builds:

- Windows (zip)

macOS and Linux support is under development.

No installation required. Download, extract, and run.

Tested on Windows 11.

---

## Windows SmartScreen

Windows may show a SmartScreen warning the first time you run TapMap.  
This is normal for new applications that are not digitally signed.

To start the program:

1. Click **More info**.  
2. Click **Run anyway**.

---

## How it runs

TapMap runs locally and opens in your browser.

The web interface runs on a local server at:

    http://127.0.0.1:8050/

If it does not open automatically, enter the address manually in your browser.

The default port is defined by `SERVER_PORT` in `config.py`.

The port can be overridden using the environment variable `TAPMAP_PORT`.

Examples:

Linux / macOS:

    TAPMAP_PORT=8060 python tapmap.py

PowerShell:

    $env:TAPMAP_PORT="8060"
    python tapmap.py
    
---

## GeoIP databases (required for map locations)

TapMap uses local MaxMind GeoLite2 databases for geolocation.  
The databases are not included in the download.

TapMap works without these files, but map locations will not be displayed.

Required files:

- GeoLite2-City.mmdb  
- GeoLite2-ASN.mmdb  

Download is free from MaxMind, but requires an account and acceptance of license terms:

```
https://dev.maxmind.com/geoip/geolite2-free-geolocation-data
```

After downloading:

1. Start TapMap.  
2. Open the **data folder** from the app.  
3. Copy the `.mmdb` files into that folder.  
4. Click **Recheck GeoIP databases**.

Update recommendation: download updated databases regularly, for example monthly.  
Redistribution is subject to the MaxMind license terms.

---

## What TapMap shows

- Services your computer connects to  
- Their approximate locations on a world map  
- Nearby clusters highlighted visually  
- Unmapped public services with missing geolocation   
- Established LAN and LOCAL services  
- Local open ports (TCP LISTEN and UDP bound)  

All data is collected locally on your machine.

---

## Why TapMap

Most computers communicate with dozens of remote systems every day.  
You usually cannot see them.

TapMap makes these connections visible within seconds.

- See unexpected connections  
- Understand where traffic goes  
- Get a quick overview of network activity  

Unexpected connections may indicate misconfiguration, background services, or unwanted software.

---

## Interface

![TapMap features](docs/images/features.gif)

### Main view
![Main view](docs/images/main-view.png)

### Actions menu
![Actions menu](docs/images/actions-menu.png)

### Unmapped services
![Unmapped services](docs/images/unmapped-services.png)

### Open ports
![Open ports](docs/images/open-ports.png)

### About
![About](docs/images/about.png)

---

## Keyboard controls

| Key | Action |
|-----|--------|
| U   | Unmapped public services |
| L   | Established LAN/LOCAL services |
| O   | Open ports |
| T   | Show cache in terminal |
| C   | Clear cache |
| R   | Recheck GeoIP databases |
| H   | Help |
| A   | About |
| ESC | Close window |

---

## Privacy

- TapMap runs locally.  
- No connection data is sent anywhere.  
- Geolocation uses local MaxMind databases.  
- If `MY_LOCATION = "auto"`, TapMap makes a small request to detect your public IP.  
- To detect offline status, TapMap performs short connection checks to 1.1.1.1 and 8.8.8.8.

---

## Configuration

TapMap reads settings from `config.py`.

Common settings:

- `SERVER_PORT`
- `MY_LOCATION`
- `POLL_INTERVAL_MS`
- `COORD_PRECISION`
- `ZOOM_NEAR_KM`

`SERVER_PORT` defines the default port used by the local Dash server.

The port can be overridden at runtime using the environment variable `TAPMAP_PORT`.

---

## Build from source

Requirements:

- Python 3.10+

Install dependencies:

```
pip install -r requirements.txt
```

Run:

```
python tapmap.py
```

Run tests:

```
pytest
```

---

## Support the project

TapMap is free and open source.

If you find it useful, consider supporting the project:

- Buy Me a Coffee  
  https://www.buymeacoffee.com/olalie  

- PayPal  
  https://www.paypal.com/donate/?hosted_button_id=ELLXBK9BY8EDU  

You can also give the project a star on GitHub.

---

## License

MIT License
