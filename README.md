# Comparateur d'images

Outil local pour determiner si deux images sont identiques, similaires ou differentes.

## Installation

Depuis ce dossier :

```powershell
pip install -r requirements.txt
```

## Lancer l'interface

```powershell
python app.py
```

Puis ouvrir :

```text
http://127.0.0.1:8765
```

## Ce que l'outil compare

- Identite stricte du fichier et des pixels.
- pHash, aHash et dHash pour reperer les images proches malgre compression ou redimensionnement.
- SSIM global pour mesurer la proximite structurelle.
- Histogrammes de couleur.
- Carte de differences avec les zones modifiees en rouge.

## Detection de doublons dans un dossier

```powershell
python app.py --find-duplicates "C:\chemin\vers\photos"
```

Le seuil par defaut est `8` sur la distance pHash. Plus le seuil est bas, plus les correspondances sont strictes.
