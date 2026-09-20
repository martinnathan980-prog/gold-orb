# Reconnaissance de caractères par le moteur intégré à Windows 10 et 11 —
# celui que le système utilise lui-même, sans rien installer, sans réseau.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File ocr_windows.ps1 DOSSIER
#
# Lit chaque image PNG du dossier et écrit, en JSON sur la sortie standard,
# une entrée par image : { "chemin": …, "mots": [ { texte, x, y, largeur,
# hauteur } ] } — les positions en pixels depuis le coin haut gauche.
#
# C'est lire_scan.py qui l'appelle ; il n'y a rien à lancer à la main. Il
# faut Windows PowerShell 5 (celui de Windows), pas PowerShell 7 : c'est lui
# qui sait parler aux composants du système.
param([Parameter(Mandatory = $true)][string]$Dossier)

$ErrorActionPreference = 'Stop'
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Attendre($operation, $type) {
    $tache = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $tache.Wait(-1) | Out-Null
    $tache.Result
}

$moteur = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $moteur) {
    $moteur = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
}
if ($null -eq $moteur) {
    Write-Error ('Aucune langue de reconnaissance de caracteres n''est installee. ' +
                 'Parametres > Heure et langue > Langue > Options de la langue > ' +
                 'Reconnaissance optique des caracteres.')
    exit 2
}

$sortie = @()
foreach ($fichier in (Get-ChildItem -Path $Dossier -Filter *.png | Sort-Object Name)) {
    $stockage = Attendre ([Windows.Storage.StorageFile]::GetFileFromPathAsync($fichier.FullName)) ([Windows.Storage.StorageFile])
    $flux = Attendre ($stockage.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decodeur = Attendre ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($flux)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $image = Attendre ($decodeur.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $resultat = Attendre ($moteur.RecognizeAsync($image)) ([Windows.Media.Ocr.OcrResult])
    $mots = @()
    foreach ($ligne in $resultat.Lines) {
        foreach ($mot in $ligne.Words) {
            $r = $mot.BoundingRect
            $mots += [pscustomobject]@{
                texte = $mot.Text; x = $r.X; y = $r.Y; largeur = $r.Width; hauteur = $r.Height
            }
        }
    }
    $sortie += [pscustomobject]@{ chemin = $fichier.Name; mots = @($mots) }
    $flux.Dispose()
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
ConvertTo-Json -Compress -Depth 4 -InputObject @($sortie)
