using System.Net.Http.Headers;
using System.Text.Json;

if (args.Length != 1)
{
    Console.Error.WriteLine("Usage: dotnet run -- <path-to-pdf>");
    return 1;
}

using var client = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:8000/"), Timeout = TimeSpan.FromMinutes(4) };
using var form = new MultipartFormDataContent();
await using var stream = File.OpenRead(args[0]);
using var fileContent = new StreamContent(stream);
fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
form.Add(fileContent, "file", Path.GetFileName(args[0]));
using var response = await client.PostAsync("api/extractions", form);
var body = await response.Content.ReadAsStringAsync();
if (!response.IsSuccessStatusCode)
{
    Console.Error.WriteLine($"Extraction failed ({(int)response.StatusCode}): {body}");
    return 1;
}

using var document = JsonDocument.Parse(body);
Console.WriteLine(JsonSerializer.Serialize(document.RootElement, new JsonSerializerOptions { WriteIndented = true }));
return 0;

