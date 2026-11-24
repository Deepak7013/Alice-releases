function Get-PreviousAliceInstallCandidates {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$SearchRoot,
        [Parameter(Mandatory = $true)]
        [string]$TargetRoot,
        [Parameter(Mandatory = $true)]
        [string]$PackageVersion
    )

    if ($PackageVersion -notmatch '^ALICE v(\d+\.\d+\.\d+)$') {
        throw "Invalid package version for install discovery: $PackageVersion"
    }
    $releaseVersion = [version]$Matches[1]
    $targetPath = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\')
    $installations = @()

    if (-not (Test-Path -LiteralPath $SearchRoot -PathType Container)) {
        return @()
    }

    foreach ($directory in Get-ChildItem -LiteralPath $SearchRoot -Directory -Filter 'Alice_v*' -ErrorAction SilentlyContinue) {
        if ([IO.Path]::GetFullPath($directory.FullName).TrimEnd('\') -ieq $targetPath) { continue }
        if ($directory.Name -notmatch '^Alice_v(\d+\.\d+\.\d+)$') { continue }

        $folderVersionText = $Matches[1]
        $versionFile = Join-Path $directory.FullName 'VERSION.txt'
        if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) { continue }
        $installedText = (Get-Content -LiteralPath $versionFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
        if ($installedText -cne "ALICE v$folderVersionText") { continue }

        $installedVersion = [version]$folderVersionText
        if ($installedVersion -gt $releaseVersion) { continue }

        $installations += [pscustomobject]@{
            Path = [IO.Path]::GetFullPath($directory.FullName)
            Version = $installedVersion
        }
    }

    return @($installations | Sort-Object -Property @{ Expression = 'Version'; Descending = $true }, @{ Expression = 'Path'; Descending = $false } | ForEach-Object { $_.Path })
}

Export-ModuleMember -Function Get-PreviousAliceInstallCandidates
