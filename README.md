# Auto 608: autko-spinner z łożyskiem 608 na masce

Model autka odtworzony ze zdjęć rzutów (przód, tył, boki, 3/4) z gniazdem na
łożysko **608** (8 × 22 × 7 mm) na masce oraz nakrętką spinnera w kształcie felgi.

![podgląd](docs/podglad_rzuty.png)

> W tym repozytorium jest też **panda wanka-wstanka** na Bambu P1S: [`panda_rolypoly/`](panda_rolypoly/README.md).

## Zawartość

| Ścieżka | Co to jest |
|---|---|
| `fusion360/Auto608/` | **Skrypt Fusion 360**, który buduje model natywnymi operacjami (szkice, wyciągnięcia, parametry) |
| `export/auto_608.step` | Gotowy złożony model (karoseria, nakrętka, łożysko ref.) do importu w Fusion (`File → Open`) |
| `export/auto_608_karoseria.stl` | Karoseria z kołami do druku (jeden element) |
| `export/auto_608_nakretka.stl` | Nakrętka spinnera (druk osobno) |
| `export/_lozysko_608_ref.stl` | Łożysko 608, tylko do podglądu |
| `cadquery_ref/car_608_cq.py` | Ta sama geometria w CadQuery; z niej wygenerowano STEP/STL |
| `tools/test_fusion_script.py` | Uruchamia skrypt Fusion na atrapie API (`tools/fake_adsk.py`) i porównuje wynik z CadQuery |
| `docs/porownanie_zdjecia_model.png` | Zdjęcia obok renderów modelu z tych samych stron |
| `docs/porownanie_bok_zdjecie.png` | Krawędzie modelu nałożone na zdjęcie z boku (kontrola proporcji) |

## Jak zbudowany jest model

* **Dolna część nadwozia** to loft przez 13 przekrojów poprzecznych: poszerzone błotniki
  nad kołami, węższe drzwi, fazowany bark z przetłoczeniem błotnika, zwężający się przód
  z fazowanymi narożnikami i zaokrąglony tył.
* **Kabina** to loft przez 8 przekrojów poziomych: zaokrąglony dach, pochylona szyba
  przednia i opadający tył (fastback).
* **Szyby i żeberka pasa na dachu** to wgłębienia 0,5 mm w „skórce” kabiny (kabina minus
  kabina wewnętrzna), więc dopasowują się do zaokrągleń.
* **Koła** wystają poza nadwozie w głębokich nadkolach. Felgi mają 5 podwójnych ramion,
  opona jest fazowana.
* **Detale:** spoiler w stylu kaczego ogona z płytkami bocznymi, wlot z przodu, listwa
  świateł, wydechy, dyfuzor i linie drzwi.

![porównanie](docs/porownanie_zdjecia_model.png)

## Uruchomienie w Fusion 360

1. `Utilities → ADD-INS → Scripts and Add-Ins` (lub `Shift+S`).
2. Zakładka **Scripts**, przycisk **+** obok *My Scripts*, wskaż folder `fusion360/Auto608`.
3. Zaznacz **Auto608** i kliknij **Run**. Skrypt otworzy nowy projekt i zbuduje model.

Model jest zbudowany w układzie **Z w górę** (X to długość, przód w X = 0; Y to szerokość;
Z to wysokość). Jeśli masz ustawione *Y up*, auto będzie leżało na boku. Zmienisz to w
`Preferences → General → Default modeling orientation → Z up`.

Po zakończeniu pojawi się komunikat. Jeśli któryś drobny detal (np. fazka, żeberka)
się nie zbudował, będzie wymieniony w ostrzeżeniach, a reszta modelu zostanie.

## Gniazdo łożyska 608

Gniazdo jest nad przednią osią (X = 15,7 mm), w płaskiej masce na wysokości Z = 13 mm.

| Parametr Fusion (`Modify → Change Parameters`) | Domyślnie | Opis |
|---|---|---|
| `lozysko_gniazdo_D` | 22,15 mm | średnica gniazda (22 mm + pasowanie) |
| `lozysko_glebokosc` | 3,0 mm | głębokość gniazda (łożysko wystaje 4 mm) |
| `lozysko_podciecie_D` | 17 mm | podcięcie pod bieżnią wewnętrzną, żeby się nie ocierała |
| `lozysko_podciecie_h` | 1,0 mm | głębokość podcięcia |

Na krawędzi gniazda jest fazka wejściowa 0,5 mm. Do wcisku na drukarce FDM zwykle
sprawdza się 22,10–22,25 mm. Warto najpierw wydrukować próbkę samego gniazda.

Nakrętka spinnera ma trzpień Ø7,95 mm wciskany w bieżnię wewnętrzną łożyska i
dystans Ø11 × 0,5 mm, który dotyka tylko bieżni wewnętrznej, więc nakrętka kręci się
swobodnie.

## Wymiary

* Nadwozie: 72 × 38,6 × 25 mm (z kołami 40 mm szerokości).
* Koła: Ø11,6 mm, rozstaw osi 44,3 mm.
* Szczyt nakrętki: około 21 mm nad podłożem.

Skalę wzięto z łożyska na zdjęciach (Ø22 mm). Stąd długość auta wychodzi około 72 mm.

Wszystkie przekroje (`LOWER_KEYS`, `CABIN_KEYS`) oraz położenie kół i detali są stałymi
na początku `Auto608.py`. Zmieniasz je i uruchamiasz skrypt ponownie. Wersja CadQuery
czyta te same stałe z pliku skryptu Fusion, więc obie wersje są zawsze zgodne.
Wymiary zmierzono z `docs/porownanie_bok_zdjecie.png`.

## Druk

* **Karoseria:** na spodzie (płaski spód, Z = 0), gniazdem do góry. Podpory tylko pod
  skrzydłem spoilera (most około 20 mm) i ewentualnie pod górą nadkoli.
* **Nakrętka:** wzorem felgi do stołu, trzpieniem do góry.
* Łożysko wciskasz w gniazdo, a potem nakrętkę w łożysko.

## Regeneracja STEP/STL bez Fusion

```bash
pip install cadquery
python3 cadquery_ref/car_608_cq.py   # zapisuje pliki do export/
python3 tools/test_fusion_script.py  # sprawdza skrypt Fusion (na atrapie API)
```

Test wykonuje prawdziwy kod `Auto608.py` na atrapie API Fusion zbudowanej na CadQuery.
Płaszczyzna XZ ma w atrapie celowo odwróconą orientację. Wynik musi być identyczny z
modelem referencyjnym (różnica objętości 0 mm³). Test sprawdza logikę skryptu (kierunki,
profile, kolejność operacji), ale nie zastępuje uruchomienia w prawdziwym Fusion.
