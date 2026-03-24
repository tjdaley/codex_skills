param(
    [Parameter(Mandatory = $true)]
    [string]$To,

    [Parameter(Mandatory = $true)]
    [string]$Subject,

    [Parameter(Mandatory = $true)]
    [string]$HtmlBodyPath,

    [string]$Attachments = "",

    [ValidateSet("draft", "send")]
    [string]$Mode = "draft"
)

$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.To = $To
$mail.Subject = $Subject
$mail.HTMLBody = Get-Content -Path $HtmlBodyPath -Raw -Encoding UTF8

if ($Attachments) {
    foreach ($attachment in ($Attachments -split ';')) {
        if ($attachment) {
            [void]$mail.Attachments.Add($attachment)
        }
    }
}

if ($Mode -eq "send") {
    $mail.Send()
} else {
    $mail.Save()
}
