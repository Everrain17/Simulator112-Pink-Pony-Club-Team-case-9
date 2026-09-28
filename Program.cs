using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json.Serialization;
using SimCore.Data;
using SimCore.Engine;
using SimCore.Entities;
using SimCore.Enums;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AIEngine;
using SimCore.Interfaces;


var builder = WebApplication.CreateBuilder(args);
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAll", policy =>
    {
        policy.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader();
    });
});
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter());
});

// === НАСТРОЙКА СТРОГОГО HTTPS (PEM) БЕЗ СКЛЕИВАНИЯ ===
string baseDir = AppDomain.CurrentDomain.BaseDirectory;
while (!File.Exists(Path.Combine(baseDir, "Program.cs")) && Directory.GetParent(baseDir) != null)
{
    baseDir = Directory.GetParent(baseDir)!.FullName;
}
if (!File.Exists(Path.Combine(baseDir, "Program.cs")))
{
    baseDir = AppDomain.CurrentDomain.BaseDirectory;
}

string certPath = Path.Combine(baseDir, "serv-112", "certs", "server.crt");
string keyPath = Path.Combine(baseDir, "serv-112", "certs", "server.key");

// Проверяем файлы. Если их нет — жестко падаем, никакой тихой работы по HTTP
if (!File.Exists(certPath))
    throw new FileNotFoundException($"❌ КРИТИЧЕСКАЯ ОШИБКА: Сертификат не найден: {certPath}");
if (!File.Exists(keyPath))
    throw new FileNotFoundException($"❌ КРИТИЧЕСКАЯ ОШИБКА: Закрытый ключ не найден: {keyPath}");

Console.WriteLine($"✅ HTTPS: Загружаем PEM-сертификаты из {certPath}");

// Загружаем PEM в систему так, чтобы Windows разрешила Kestrel использовать закрытый ключ
using var ephemeralCert = X509Certificate2.CreateFromPem(File.ReadAllText(certPath), File.ReadAllText(keyPath));
var certificate = new X509Certificate2(ephemeralCert.Export(X509ContentType.Pkcs12), (string?)null, X509KeyStorageFlags.PersistKeySet);

builder.WebHost.ConfigureKestrel(options =>
{
    // Слушаем порт 5000 для любых IP (чтобы заказчик тоже мог зайти)
    options.ListenAnyIP(5000, listenOptions =>
    {
        listenOptions.UseHttps(certificate);
    });
});
// === КОНЕЦ HTTPS КОНФИГУРАЦИИ ===

var app = builder.Build();

app.UseDefaultFiles();
app.UseStaticFiles();
app.UseCors("AllowAll");
app.UseWebSockets();
List<StreetWithHouses> addresses = new List<StreetWithHouses>();
SimulationEngine? engine = null;
AiClient ai = new AiClient();
Timer? simulationTimer = null;
TtsService tts = new TtsService(
    baseUrl: "https://localhost:8000/v1",
    modelName: "silero",
    voice: "aidar"
);
bool isSimulationRunning = false;
object simulationLock = new object();
string lastAiResponse = "Симуляция ожидает запуска преподавателем.";
string internalToken = Environment.GetEnvironmentVariable("SYSTEM112_INTERNAL_TOKEN") ?? "system112-dev-internal";

bool IsInternalRequest(HttpContext context)
{
    return string.Equals(
        context.Request.Headers["X-System112-Internal"].ToString(),
        internalToken,
        StringComparison.Ordinal
    );
}

static bool TryParseIncidentType(string code, out IncidentType value)
{
    return Enum.TryParse(code?.Trim(), ignoreCase: true, out value);
}

static bool TryParseServiceCode(string code, out ServiceType value)
{
    value = default;
    string normalized = (code ?? string.Empty).Trim();
    if (string.IsNullOrWhiteSpace(normalized)) return false;
    value = normalized switch
    {
        "101" => ServiceType.MCHS,
        "102" => ServiceType.POLICE,
        "103" => ServiceType.AMBULANCE,
        "104" => ServiceType.GAS,
        _ => default
    };
    if (normalized is "101" or "102" or "103" or "104") return true;
    return Enum.TryParse(normalized, ignoreCase: true, out value);
}

static bool TryParseClassifierTagCode(string code, out ClassifierTag value)
{
    return Enum.TryParse(code?.Trim(), ignoreCase: true, out value);
}

static string GetServiceDisplayName(ServiceType service)
{
    return service switch
    {
        ServiceType.MCHS => "101 — МЧС",
        ServiceType.POLICE => "102 — Полиция",
        ServiceType.AMBULANCE => "103 — Скорая помощь",
        ServiceType.GAS => "104 — Газовая служба",
        ServiceType.ANTITERROR => "Антитеррор",
        ServiceType.MOSLIFT => "Мослифт",
        ServiceType.DEPT_ZHKH => "Департамент ЖКХ",
        ServiceType.TSOMP => "ЦОДД / транспорт",
        ServiceType.MOSVODOCANAL => "Мосводоканал",
        ServiceType.ZODD => "ЦОДД",
        ServiceType.AUTOROADS => "Автомобильные дороги",
        ServiceType.GORMOST => "Гормост",
        ServiceType.MOEK => "МОЭК",
        ServiceType.MOESK => "МОЭСК",
        ServiceType.MGTS => "МГТС",
        ServiceType.METRO => "Метрополитен",
        ServiceType.MOSGORTRANS => "Мосгортранс",
        ServiceType.MOSCOLLECTOR => "Москоллектор",
        ServiceType.MOSVODOSTOK => "Мосводосток",
        ServiceType.MSPPN => "МСППН",
        ServiceType.DEPECO => "Департамент природопользования",
        ServiceType.DEP_TSZN => "Департамент труда и социальной защиты",
        ServiceType.RZD => "РЖД",
        _ => service.ToString()
    };
}

static string? GetServiceDispatchCode(ServiceType service)
{
    return service switch
    {
        ServiceType.MCHS => "101",
        ServiceType.POLICE => "102",
        ServiceType.AMBULANCE => "103",
        ServiceType.GAS => "104",
        _ => null
    };
}
string FindGpkgFile()
{
    string? currentDir = Directory.GetCurrentDirectory();
    while (currentDir != null)
    {
        string gpkgPath = Path.Combine(currentDir, "map.gpkg");
        if (File.Exists(gpkgPath))
        {
            return gpkgPath;
        }
        var parentDir = Directory.GetParent(currentDir);
        if (parentDir == null) break;
        currentDir = parentDir.FullName;
    }
    return "map.gpkg";
}
string gpkgPath = FindGpkgFile();
Console.WriteLine($"📍 Ищем GPKG по пути: {gpkgPath}");
addresses = File.Exists(gpkgPath)
    ? new GpkgParser().ParseAddresses(gpkgPath)
    : new List<StreetWithHouses>
    {
        new("ул. Профсоюзная", "residential", new List<HouseReference>
        {
            new("5/9", 55.655, 37.575, null)
        })
    };
if (File.Exists(gpkgPath))
{
    Console.WriteLine($"✅ GPKG файл найден и загружен: {gpkgPath}");
}
else
{
    Console.WriteLine($"⚠️ GPKG файл не найден, используем тестовые данные");
}
Console.WriteLine("\n==================================================================");
Console.WriteLine("=== 🚀 СТРИМИНГОВЫЙ API СЕРВЕР СИМУЛЯТОРА ГОТОВ К РАБОТЕ ===");
Console.WriteLine("=== Протокол связи: WEBSOCKETS + DELTA TIME (0.1с) ====");
Console.WriteLine("==================================================================\n");
app.MapPost("/api/start", (HttpContext context, [FromBody] StartSimulationRequest request) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();
    lock (simulationLock)
    {
        if (isSimulationRunning)
        {
            simulationTimer?.Dispose();
        }
        var rng = new Random(request.Seed);
        engine = new SimulationEngine(
            addresses,
            rng,
            request.Profile,
            request.CallAnswerTimeSeconds,
            request.SLATimeSeconds,
            request.EndCallTimeSeconds,
            request.Seed,
            request.Criteria
        );
        isSimulationRunning = true;
        lastAiResponse = "Линия свободна. Ожидайте вызов.";
        simulationTimer = new Timer(state =>
        {
            lock (simulationLock)
            {
                if (engine == null) return;
                var worldState = engine.Update(0.1);
            }
        }, null, 100, 100);
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"▶️ Симуляция запущена. Seed: {request.Seed}");
        Console.ResetColor();
        return Results.Json(new
        {
            success = true,
            seed = request.Seed,
            profile = request.Profile.ToString(),
            timings = new
            {
                callAnswer = request.CallAnswerTimeSeconds,
                sla = request.SLATimeSeconds,
                endCall = request.EndCallTimeSeconds
            }
        });
    }
});
app.MapGet("/api/classifier", () =>
{
    lock (simulationLock)
    {
        var profiles = engine?.GetClassifier() ?? ClassifierLoader.LoadClassifier();
        var incidentTypes = profiles
            .GroupBy(p => p.IncidentType)
            .Select(g =>
            {
                var first = g.First();
                return new
                {
                    code = g.Key.ToString(),
                    name = g.Key.GetDisplayName(),
                    ekpCode = g.Select(p => p.EkpCode)
                        .FirstOrDefault(x => !string.IsNullOrWhiteSpace(x)),
                    subgroup = first.Subgroup,
                    mainService = first.MainService.ToString(),
                    // Public operator catalog: do not expose GroundTruth-like
                    // tag/service requirements to the student runtime.
                    additionalServices = new List<string>(),
                    criticalTags = new List<string>(),
                    scenarioDescription = string.Empty,
                    profileCount = g.Count()
                };
            })
            .OrderBy(x => x.code)
            .ToList();

        var services = Enum.GetValues<ServiceType>()
            .Select(service => new
            {
                code = service.ToString(),
                dispatchCode = GetServiceDispatchCode(service),
                name = GetServiceDisplayName(service),
                description = $"Каноническая служба SimCore: {service}"
            })
            .ToList();

        return Results.Json(new
        {
            schemaVersion = 1,
            incidentTypes,
            services
        });
    }
});
app.MapGet("/api/teacher/ground-truth/{callId}", (HttpContext context, string callId) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();
    lock (simulationLock)
    {
        if (engine == null)
            return Results.NotFound("Симуляция не запущена");
        var groundTruth = OperatorAuditEngine.GetGroundTruth(callId, engine.GetActiveCalls(), engine.GetAllIncidents());
        if (groundTruth == null)
            return Results.NotFound("Звонок не найден");
        return Results.Json(groundTruth);
    }
});

app.MapGet("/api/call-snapshot/{callId}", (HttpContext context, string callId) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();

    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена.");

        var snapshot = engine.GetCallSnapshot(callId);

        if (snapshot == null)
            return Results.NotFound("Звонок не найден");

        return Results.Json(snapshot);
    }
});

app.MapPost("/api/stop", (HttpContext context) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();
    lock (simulationLock)
    {
        simulationTimer?.Dispose();
        simulationTimer = null;
        isSimulationRunning = false;
        lastAiResponse = "Симуляция остановлена.";
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("Симуляция остановлена преподавателем.");
        Console.ResetColor();
        return Results.Json(new { success = true });
    }
});
app.MapGet("/api/state", () =>
{
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.Json(new { isRunning = false });
        var worldState = engine.GetCurrentState();
        var publicIncidents = worldState.AllIncidents.Select(i => new
        {
            id = i.Id,
            address = i.Address,
            state = i.State.ToString(),
            severity = i.Severity,
            timeElapsedSeconds = i.TimeElapsedSeconds,
            description = i.Description
        }).ToList();
        return Results.Json(new
        {
            isRunning = true,
            elapsedSeconds = worldState.ElapsedSeconds,
            elapsedTicks = worldState.ElapsedTicks,
            activeCalls = worldState.ActiveCalls.Select(c => new
            {
                id = c.Id,
                incidentId = c.IncidentId,
                studentId = c.StudentId ?? "Свободен",
                c.TimeRemainingSeconds,
                c.SilenceDurationSeconds,
                c.Caller,
                cardState = c.CardState.ToString(),
                c.TimeToConfirmSeconds
            }).ToList(),
            allIncidents = publicIncidents,
            systemEventsLog = worldState.SystemEventsLog,
            lastAiResponse = lastAiResponse
        });
    }
});
app.MapGet("/api/available-calls", () =>
{
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.Json(new { availableCalls = new List<object>() });

        var worldState = engine.GetCurrentState();
        var freeCalls = worldState.ActiveCalls
            .Where(c => c.StudentId == null)
            .Select(c => new
            {
                callId = c.Id,
                callerPhone = c.Caller.PhoneNumber
            })
            .ToList();

        return Results.Json(new { availableCalls = freeCalls });
    }
});

app.MapPost(
    "/api/release-call",
    (
        HttpContext context,
        [FromBody] ReleaseCallRequest request
    ) =>
    {
        if (!IsInternalRequest(context))
            return Results.Unauthorized();

        if (string.IsNullOrWhiteSpace(request.CallId))
            return Results.BadRequest(
                "CallId не указан."
            );

        lock (simulationLock)
        {
            if (!isSimulationRunning || engine == null)
                return Results.BadRequest(
                    "Симуляция не запущена."
                );

            bool success =
                engine.ReleaseStudentFromCallSync(
                    request.CallId
                );

            if (!success)
                return Results.NotFound(
                    "Звонок не найден."
                );

            return Results.Ok(
                new
                {
                    callId = request.CallId,
                    released = true
                }
            );
        }
    }); 

app.MapPost("/api/accept-call", (HttpContext context, [FromBody] AcceptCallRequest request) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена.");
        if (string.IsNullOrWhiteSpace(request.StudentId))
            return Results.BadRequest("StudentId не указан");
        bool success = engine.AssignStudentToCall(request.CallId, request.StudentId);
        if (!success)
            return Results.Conflict("Звонок не найден или уже занят другим студентом");
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine($"👨‍🎓 Студент {request.StudentId} принял звонок {request.CallId}");
        Console.ResetColor();
        return Results.Json(new { success = true, callId = request.CallId, studentId = request.StudentId });
    }
});
app.MapPost("/api/inject", (HttpContext context, [FromBody] InjectCallRequest request) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();

    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена.");

        if (!TryParseIncidentType(request.IncidentTypeCode, out var incidentType))
            return Results.BadRequest($"Неизвестный IncidentType: {request.IncidentTypeCode}");

        var profile = engine.GetClassifier()
            .FirstOrDefault(x => x.IncidentType == incidentType);
        if (profile == null)
            return Results.BadRequest($"Для IncidentType {incidentType} нет профиля в incident-classifier.json");

        var requiredServices = new List<ServiceType>();
        foreach (var code in request.RequiredServiceCodes ?? new List<string>())
        {
            if (!TryParseServiceCode(code, out var service))
                return Results.BadRequest($"Неизвестный ServiceType: {code}");
            if (!requiredServices.Contains(service))
                requiredServices.Add(service);
        }
        if (requiredServices.Count == 0)
        {
            requiredServices.Add(profile.MainService);
            requiredServices.AddRange(profile.AdditionalServices.Where(x => !requiredServices.Contains(x)));
        }

        var criticalTags = new List<ClassifierTag>();
        foreach (var code in request.CriticalTagCodes ?? new List<string>())
        {
            if (!TryParseClassifierTagCode(code, out var tag))
                return Results.BadRequest($"Неизвестный ClassifierTag: {code}");
            if (tag != ClassifierTag.None && !criticalTags.Contains(tag))
                criticalTags.Add(tag);
        }
        if (criticalTags.Count == 0)
            criticalTags.AddRange(profile.CriticalTags);

        var optionalTags = new List<ClassifierTag>();
        foreach (var code in request.OptionalTagCodes ?? new List<string>())
        {
            if (!TryParseClassifierTagCode(code, out var tag))
                return Results.BadRequest($"Неизвестный ClassifierTag: {code}");
            if (tag != ClassifierTag.None && !optionalTags.Contains(tag))
                optionalTags.Add(tag);
        }

        string ekpCode = string.IsNullOrWhiteSpace(request.EkpCode) ? profile.EkpCode : request.EkpCode;
        string ekpName = string.IsNullOrWhiteSpace(request.EkpName) ? profile.Name : request.EkpName;

        var injected = TeacherEngine.InjectCall(
            incidentType,
            request.Severity,
            request.InitialPanic,
            requiredServices,
            request.Description ?? profile.ScenarioDescription,
            request.Address ?? string.Empty,
            request.Lat,
            request.Lon,
            request.CustomUtterance,
            request.TeacherComment,
            criticalTags,
            optionalTags,
            ekpCode,
            ekpName,
            engine.GetRng(),
            engine.GetTotalElapsedSeconds(),
            engine.GetAllIncidents(),
            engine.GetActiveCalls(),
            engine.GetSystemEventsLog(),
            engine.GetSlaTimeSeconds(),
            engine.GetEndCallTimeSeconds(),
            engine.GetNextCallNumber,
            engine.TriggerResetIdleTimers
        );

        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine($"👨‍🏫 [ПРЕПОДАВАТЕЛЬ] Инжектирован звонок {injected.ActiveCall.Id}: {incidentType} по адресу {injected.Incident.Address}");
        Console.ResetColor();

        return Results.Json(new
        {
            success = true,
            callId = injected.ActiveCall.Id,
            incidentId = injected.Incident.Id,
            incidentTypeCode = incidentType.ToString(),
            ekpCode = ekpCode,
            ekpName = ekpName,
            requiredServiceCodes = requiredServices.Select(x => x.ToString()).ToList(),
            criticalTagCodes = criticalTags.Select(x => x.ToString()).ToList()
        });
    }
});
app.MapPost("/api/teacher-intervene", (HttpContext context, [FromBody] UpdateTeacherCommentRequest request) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена.");
        if (string.IsNullOrWhiteSpace(request.CallId) || string.IsNullOrWhiteSpace(request.Comment))
            return Results.BadRequest("CallId и Comment обязательны");
        bool success = TeacherEngine.UpdateTeacherComment(
            request.CallId,
            request.Comment,
            engine.GetActiveCalls(),
            engine.GetSystemEventsLog(),
            engine.GetTotalElapsedSeconds()
        );
        if (!success)
            return Results.NotFound("Активный звонок не найден");
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"👨‍🏫 [ПРЕПОДАВАТЕЛЬ] Вмешательство в звонок {request.CallId}: {request.Comment}");
        Console.ResetColor();
        return Results.Json(new { success = true, message = "Инструкция преподавателя принята и будет применена в следующей реплике бота" });
    }
});

app.MapPost("/api/complete-call", (
    HttpContext context,
    [FromBody] CompleteCallRequest request) =>
{
    if (!IsInternalRequest(context))
        return Results.Unauthorized();

    if (string.IsNullOrWhiteSpace(request.CallId))
        return Results.BadRequest("CallId не указан.");

    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest(
                "Симуляция не запущена."
            );

        var success =
            engine.CompleteCallSync(
                request.CallId
            );

        if (!success)
            return Results.NotFound(
                "Звонок не найден."
            );

        return Results.Ok(
            new
            {
                callId = request.CallId,
                closed = true
            }
        );
    }
});

app.MapPost("/api/card-submit", (HttpContext context, [FromBody] CardSubmitRequest request) =>
{
    if (!IsInternalRequest(context)) return Results.Unauthorized();
    lock (simulationLock)
    {
        if (engine == null)
            return Results.BadRequest("Симуляция не запущена");
        engine.UpdateCardState(request.CallId, CardState.SentToServices);
        var worldState = engine.GetCurrentState();
        var call = worldState.ActiveCalls.FirstOrDefault(c => c.Id == request.CallId);
        if (call == null)
            return Results.NotFound("Звонок не найден");
        double timeSinceCallStart = worldState.ElapsedSeconds - call.CallStartedAtGlobalSeconds;
        return Results.Json(new
        {
            success = true,
            callId = request.CallId,
            cardSubmissionDurationSeconds = timeSinceCallStart
        });
    }
});
app.MapPost("/api/validate-card-text", async (HttpContext context, [FromBody] ValidateCardTextRequest request) =>
{
    if (!IsInternalRequest(context)) return Results.Unauthorized();
    SimulationEngine currentEngine;
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена.");
        currentEngine = engine;
    }
    var groundTruth = OperatorAuditEngine.GetGroundTruth(request.CallId, currentEngine.GetActiveCalls(), currentEngine.GetAllIncidents());
    if (groundTruth == null)
        return Results.NotFound("Звонок не найден");
    var analysis = await ai.AnalyzeCardTextAsync(request.Text, groundTruth);
    return Results.Json(analysis);
});
app.MapGet("/api/call-analysis/{callId}", (string callId) =>
{
    lock (simulationLock)
    {
        if (engine == null)
            return Results.NotFound("Симуляция не запущена");
        if (engine.GetCallAnalysisResults().TryGetValue(callId, out var analysis))
        {
            return Results.Json(analysis);
        }
        return Results.NotFound("Звонок не найден");
    }
});
app.MapPost("/api/set-last-call-id", (HttpContext context, [FromBody] int lastId) =>
{
    if (!IsInternalRequest(context)) return Results.Unauthorized();
    lock (simulationLock)
    {
        if (engine != null)
        {
            engine.SetCallCounter(lastId);
            return Results.Json(new { success = true, lastCallIdSet = lastId });
        }
        return Results.BadRequest("Симуляция еще не инициализирована движком.");
    }
});
app.MapGet("/api/load-all-saved-cards", () =>
{
    string sessionsFolder = Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "sessions");
    if (!Directory.Exists(sessionsFolder))
    {
        return Results.Json(new List<object>());
    }
    try
    {
        var files = Directory.GetFiles(sessionsFolder, "*.json");
        var savedCards = new List<JsonElement>();
        foreach (var file in files)
        {
            string content = File.ReadAllText(file, Encoding.UTF8);
            var doc = JsonDocument.Parse(content);
            savedCards.Add(doc.RootElement.Clone());
        }
        return Results.Json(savedCards);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"⚠️ Ошибка парсинга папки карточек: {ex.Message}");
        return Results.Json(new List<object>());
    }
});
app.MapPost("/api/save-session-file", async (HttpContext context) =>
{
    try
    {
        using var reader = new StreamReader(context.Request.Body);
        string jsonRaw = await reader.ReadToEndAsync();
        using var doc = JsonDocument.Parse(jsonRaw);
        var root = doc.RootElement;
        string callId = "CALL-UNKNOWN";
        if (root.TryGetProperty("callId", out var cIdProp)) callId = cIdProp.GetString() ?? "CALL-UNKNOWN";
        else if (root.TryGetProperty("CallId", out var cIdPropUpper)) callId = cIdPropUpper.GetString() ?? "CALL-UNKNOWN";
        string sessionsFolder = Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "sessions");
        if (!Directory.Exists(sessionsFolder))
        {
            Directory.CreateDirectory(sessionsFolder);
        }
        string filePath = Path.Combine(sessionsFolder, $"{callId}.json");
        await File.WriteAllTextAsync(filePath, jsonRaw, Encoding.UTF8);
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"💾 [ЯДРО] Карточка {callId} успешно зафиксирована в файл: wwwroot/sessions/{callId}.json");
        Console.ResetColor();
        return Results.Json(new { success = true, path = $"sessions/{callId}.json" });
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"❌ [ОШИБКА СОХРАНЕНИЯ ФАЙЛА]: {ex.Message}");
        Console.ResetColor();
        return Results.StatusCode(500);
    }
});
app.MapGet("/api/addresses", () => Results.Json(addresses));
app.MapGet("/api/meta", () => Results.Json(new
{
    schemaVersion = 1,
    incidentTypes = Enum.GetValues<IncidentType>()
        .Select(x => new { code = x.ToString(), name = x.GetDisplayName() })
        .ToList(),
    serviceTypes = Enum.GetValues<ServiceType>()
        .Select(x => new
        {
            code = x.ToString(),
            dispatchCode = GetServiceDispatchCode(x),
            name = GetServiceDisplayName(x)
        })
        .ToList()
}));
app.MapPost("/api/supplement-call", (HttpContext context, [FromBody] SupplementCallRequest request) =>
{
    if (!IsInternalRequest(context)) return Results.Unauthorized();
    lock (simulationLock)
    {
        if (!isSimulationRunning || engine == null)
            return Results.BadRequest("Симуляция не запущена");
        var result = OperatorAuditEngine.ExecuteSupplementCall(
            request.CallId,
            request.AddedServices,
            request.CurrentTimeSeconds,
            engine.GetSlaTimeSeconds(),
            engine.GetActiveCalls(),
            engine.GetAllIncidents(),
            engine.GetActiveSessions(),
            engine.GetCallAnalysisResults()
        );
        return Results.Json(result);
    }
});
app.Use(async (context, next) =>
{
    if (context.Request.Path == "/api/stream-call")
    {
        if (context.WebSockets.IsWebSocketRequest)
        {
            using var webSocket = await context.WebSockets.AcceptWebSocketAsync();
            await HandleCallStreamingAsync(webSocket, context);
        }
        else
        {
            context.Response.StatusCode = 400;
        }
    }
    else
    {
        await next(context);
    }
});
async Task HandleCallStreamingAsync(WebSocket webSocket, HttpContext context)
{
    var buffer = new byte[1024 * 4];
    double silenceTracker = 0.0;
    string accumulatedOperatorText = "";
    string callId = context.Request.Query["callId"];
    if (string.IsNullOrEmpty(callId))
    {
        await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "CallId is required", CancellationToken.None);
        return;
    }
    var telemetryTask = Task.Run(async () =>
    {
        while (webSocket.State == WebSocketState.Open)
        {
            await Task.Delay(100);
            silenceTracker += 0.1;
            string? jsonToSend = null;
            lock (simulationLock)
            {
                if (engine != null && !string.IsNullOrEmpty(callId))
                {
                    var state = engine.GetCurrentState();
                    var call = state.ActiveCalls.FirstOrDefault(c => c.Id == callId);
                    if (call != null)
                    {
                        var telemetryData = new
                        {
                            type = "telemetry_update",
                            panicLevel = call.Caller.PanicLevel,
                            silenceDurationSeconds = silenceTracker,
                            hasGivenAddress = call.Caller.HasGivenAddress,
                            hasGivenVictimsInfo = call.Caller.HasGivenVictimsInfo,
                            accumulatedWordsCount = accumulatedOperatorText.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length
                        };
                        jsonToSend = JsonSerializer.Serialize(telemetryData);
                    }
                }
            }
            if (jsonToSend != null && webSocket.State == WebSocketState.Open)
            {
                var outBuffer = Encoding.UTF8.GetBytes(jsonToSend);
                await webSocket.SendAsync(new ArraySegment<byte>(outBuffer), WebSocketMessageType.Text, true, CancellationToken.None);
            }
        }
    });
    try
    {
        while (webSocket.State == WebSocketState.Open)
        {
            var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
            if (result.MessageType == WebSocketMessageType.Text)
            {
                string incomingJson = Encoding.UTF8.GetString(buffer, 0, result.Count);
                using var doc = JsonDocument.Parse(incomingJson);
                var root = doc.RootElement;
                string type = root.GetProperty("type").GetString() ?? "";
                string text = root.GetProperty("text").GetString() ?? "";
                if (!string.IsNullOrWhiteSpace(text))
                {
                    if (type == "interim")
					{
						accumulatedOperatorText = text;
						silenceTracker = 0.0;

						lock (simulationLock)
						{
							if (!string.IsNullOrEmpty(callId) && engine != null)
							{
								OperatorAuditEngine.ForceUpdateLastUtterance(
									callId,
									text,
									engine.GetActiveSessions()
								);
							}
						}
					}
                    else if (type == "final")
                    {
                        string currentCallIdCopy = callId ?? "";
                        accumulatedOperatorText = "";
                        if (!string.IsNullOrEmpty(currentCallIdCopy))
                        {
                            ActiveCall? call = null;
                            Incident? incident = null;
                            lock (simulationLock)
                            {
                                if (engine != null)
                                {
                                    // СТРОГИЙ ПОИСК: ищем только тот звонок, который прилетел с фронта!
                                    call = engine.GetActiveCalls().FirstOrDefault(c => c.Id == currentCallIdCopy);
                                    if (call != null)
                                    {
                                        incident = engine.GetAllIncidents().FirstOrDefault(i => i.Id == call.IncidentId);
                                    }
                                    else
                                    {
                                        Console.ForegroundColor = ConsoleColor.Red;
                                        Console.WriteLine($"[ОШИБКА ИИ] Сокет прислал CallId '{currentCallIdCopy}', но в памяти ядра такого звонка НЕТ!");
                                        Console.ResetColor();
                                    }
                                }
                            }
                            // Работаем только если сквозной ID совпал на 100% и данные найдены
                            if (call != null && incident != null)
                            {
                                string incidentDesc = incident.Description ?? "Неизвестно";
                                // 1. Асинхронный ИИ-анализ действий
                                var replyAnalysis = await ai.AnalyzeOperatorReplyAsync(text, incidentDesc);
                                lock (simulationLock)
                                {
                                    if (engine != null && replyAnalysis != null)
                                    {
                                        OperatorAuditEngine.ApplyAnalysisResult(call.Id, replyAnalysis, engine.GetTotalElapsedSeconds(), engine.GetActiveCalls(), engine.GetSystemEventsLog(), engine.GetSystemEventsLog());
                                        double currentCallSeconds = engine.GetTotalElapsedSeconds() - call.CallStartedAtGlobalSeconds;
                                        OperatorAuditEngine.UpdateCallAnalysis(call.Id, replyAnalysis, currentCallSeconds, engine.GetCallAnalysisResults());
                                    }
                                }
                                lock (simulationLock)
                                {
                                    if (engine != null &&
                                        engine.GetActiveSessions().TryGetValue(currentCallIdCopy, out var session))
                                    {
                                        lock (session)
                                        {
                                            session.Utterances.Add(
                                                new Utterance
                                                {
                                                    Speaker = SpeakerRole.Operator,
                                                    Text = text,
                                                    Timestamp = DateTime.UtcNow
                                                }
                                            );
                                        }
                                    }
                                }
                                // 2. Сборка промпта строго по живому контексту
                                AIPromptPayload? payload = null;
                                lock (simulationLock)
                                {
                                    if (engine != null)
                                    {
                                        var hiddenFacts = incident.HiddenFacts;
                                        var emptySuggestedTopics = new List<string>();
                                        var lastAction = engine.GetSystemEventsLog().LastOrDefault(a => a.Contains(call.Id)) ?? "none";
                                        List<Utterance> dialogueHistory = new();

                                        if (engine.GetActiveSessions().TryGetValue(call.Id, out var currentSession))
                                        {
                                            lock (currentSession)
                                            {
                                                dialogueHistory = currentSession.Utterances.ToList();
                                            }
                                        }

                                        payload = AiPromptBuilder.BuildPrompt(
                                            incident,
                                            call.Caller,
                                            hiddenFacts,
                                            text,
                                            emptySuggestedTopics,
                                            dialogueHistory,
                                            (int)engine.GetTotalElapsedSeconds(),
                                            engine.GetTotalElapsedSeconds()
                                        );
                                    }
                                }
                                if (payload != null && !string.IsNullOrWhiteSpace(payload.TextPrompt))
                                {
                                    if (webSocket.State == WebSocketState.Open)
                                    {
                                        var debugData = new { type = "debug_prompt", text = payload.TextPrompt };
                                        var debugBuffer = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(debugData));
                                        await webSocket.SendAsync(new ArraySegment<byte>(debugBuffer), WebSocketMessageType.Text, true, CancellationToken.None);
                                    }
                                    var textBuffer = new StringBuilder();
                                    async IAsyncEnumerable<string> InterceptAndAccumulateTokens(IAsyncEnumerable<string> sourceStream)
                                    {
                                        await foreach (var token in sourceStream)
                                        {
                                            textBuffer.Append(token);
                                            yield return token;
                                        }
                                    }
                                    var rawAiStream = ai.GenerateResponseStreamingAsync(payload.TextPrompt, text);
                                    var interceptedStream = InterceptAndAccumulateTokens(rawAiStream);
                                    string genderToSend = incident.HiddenFacts?.Gender;
                                    var hFacts = incident.HiddenFacts;
                                    if (hFacts != null)
                                    {
                                        string who = (hFacts.WhoIsCalling ?? "").ToLower();
                                        string sym = (hFacts.Symptoms ?? "").ToLower();
                                    }
                                    // Модификатор скорости речи вытаскиваем из С# ядра CallerState (завязан напрямую на шкалу паники)
                                    double speedToSend = call.Caller?.SpeedModifier ?? 1.2;
                                    // 3. Стриминг звука (Вызываем новый асинхронный метод с передачей контекста)
                                    if (webSocket.State == WebSocketState.Open)
                                    {
                                        await foreach (var audioChunk in tts.SynthesizeStreamingWithContextAsync(interceptedStream, genderToSend, speedToSend))
                                        {
                                            await webSocket.SendAsync(
                                                new ArraySegment<byte>(audioChunk),
                                                WebSocketMessageType.Binary,
                                                true,
                                                CancellationToken.None);
                                        }
                                    }
                                    // 4. Логгирование и отправка текста на фронтенд
                                    string fullResponse = textBuffer.ToString().Trim();

                                    lock (simulationLock)
                                    {
                                        lastAiResponse = fullResponse;

                                        if (engine != null &&
                                            !string.IsNullOrWhiteSpace(fullResponse) &&
                                            engine.GetActiveSessions().TryGetValue(
                                                currentCallIdCopy,
                                                out var session))
                                        {
                                            lock (session)
                                            {
                                                session.Utterances.Add(
                                                    new Utterance
                                                    {
                                                        Speaker = SpeakerRole.Caller,
                                                        Text = fullResponse,
                                                        Timestamp = DateTime.UtcNow
                                                    }
                                                );
                                            }
                                        }
                                    }
                                    if (webSocket.State == WebSocketState.Open && !string.IsNullOrWhiteSpace(fullResponse))
                                    {
                                        var responseData = new { type = "response", text = fullResponse };
                                        var outBuffer = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(responseData));
                                        await webSocket.SendAsync(new ArraySegment<byte>(outBuffer), WebSocketMessageType.Text, true, CancellationToken.None);
                                    }
                                }
                            }
                        }
                    }
                }
            }
            else if (result.MessageType == WebSocketMessageType.Close)
            {
                await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
            }
        }
    }
    catch
    {
    }
    await telemetryTask;
}
app.Run();
public record StartSimulationRequest(
    int Seed,
    DdsProfile Profile = DdsProfile.Universal_112,
    int CallAnswerTimeSeconds = 30,
    int SLATimeSeconds = 75,
    int EndCallTimeSeconds = 420,
    EvaluationCriteria Criteria = null,
    int? SessionId = null
);
public record CloseCallRequest(string CallId);
public record DispatchServicesRequest(string CallId, List<ServiceType> Services);
public record InjectCallRequest(
    string IncidentTypeCode,
    int Severity = 50,
    int InitialPanic = 50,
    List<string>? RequiredServiceCodes = null,
    List<string>? CriticalTagCodes = null,
    List<string>? OptionalTagCodes = null,
    string? EkpCode = null,
    string? EkpName = null,
    string Description = "",
    string Address = "",
    double Lat = 0.0,
    double Lon = 0.0,
    string? CustomUtterance = null,
    string? TeacherComment = null
);
public record CardSubmitRequest(string CallId);
public record AcceptCallRequest(string CallId, string StudentId, string? PhoneNumber = null);
public record UpdateTeacherCommentRequest(string CallId, string Comment);
public record ValidateCardTextRequest(string CallId, string Text);
public record SupplementCallRequest(string CallId, List<ServiceType> AddedServices, double CurrentTimeSeconds);
public class ReleaseCallRequest
{
    public string CallId { get; set; } = string.Empty;
}