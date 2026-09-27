using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using SimCore.Entities;
using SimCore.Enums;

namespace SimCore.Engine
{
    public static class ClassifierLoader
    {
        public static List<IncidentProfile> LoadClassifier()
        {
            var classifierList = new List<IncidentProfile>();

            string classifierPath = FindClassifierFile();

            if (!File.Exists(classifierPath))
            {
                Console.WriteLine(
                    $"⚠️ Классификатор не найден по пути: {classifierPath}. " +
                    "Используем пустой классификатор."
                );

                return classifierList;
            }

            try
            {
                string json = File.ReadAllText(classifierPath);

                var options = new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                };

                var profiles =
                    JsonSerializer.Deserialize<List<IncidentProfileJson>>(
                        json,
                        options
                    );

                if (profiles == null || profiles.Count == 0)
                {
                    Console.WriteLine("⚠️ Классификатор пуст.");
                    return classifierList;
                }

                foreach (var p in profiles)
                {
                    try
                    {
                        var profile = new IncidentProfile(
                            EkpCode: p.EkpCode ?? "UNKNOWN",

                            Name: p.Name ?? "Неизвестно",

                            Subgroup: p.Subgroup ?? "",

                            IncidentType: ParseIncidentType(p.IncidentType),

                            MainService: ParseServiceType(p.MainService),

                            AdditionalServices:
                                p.AdditionalServices?
                                    .Select(ParseServiceType)
                                    .Where(x => x != ServiceType.MCHS ||
                                                p.MainService == "MCHS" ||
                                                p.AdditionalServices!.Contains("MCHS"))
                                    .Distinct()
                                    .ToList()
                                ?? new List<ServiceType>(),

                            CriticalTags:
                                p.CriticalTags?
                                    .Select(ParseClassifierTag)
                                    .Where(x => x != ClassifierTag.None)
                                    .Distinct()
                                    .ToList()
                                ?? new List<ClassifierTag>(),

                            ScenarioDescription:
                                string.IsNullOrWhiteSpace(p.ScenarioDescription)
                                    ? "Описание сценария отсутствует"
                                    : p.ScenarioDescription
                        );

                        classifierList.Add(profile);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine(
                            $"⚠️ Не удалось загрузить профиль " +
                            $"'{p.Name ?? "без имени"}': {ex.Message}"
                        );
                    }
                }

                Console.WriteLine(
                    $"✅ УСПЕШНО: Загружено {classifierList.Count} " +
                    $"типов происшествий ЕКП из классификатора."
                );
            }
            catch (JsonException ex)
            {
                Console.WriteLine(
                    $"❌ Ошибка JSON классификатора: {ex.Message}"
                );
            }
            catch (Exception ex)
            {
                Console.WriteLine(
                    $"❌ Ошибка загрузки классификатора: {ex.Message}"
                );
            }

            return classifierList;
        }

        private static string FindClassifierFile()
        {
            string? currentDir = Directory.GetCurrentDirectory();

            while (currentDir != null)
            {
                string path = Path.Combine(
                    currentDir,
                    "incident-classifier.json"
                );

                if (File.Exists(path))
                    return path;

                var parent = Directory.GetParent(currentDir);

                if (parent == null)
                    break;

                currentDir = parent.FullName;
            }

            return "incident-classifier.json";
        }

        private static IncidentType ParseIncidentType(string? type)
        {
            if (string.IsNullOrWhiteSpace(type))
            {
                Console.WriteLine(
                    "⚠️ IncidentType не указан. " +
                    "Используется OtherIncident."
                );

                return IncidentType.OtherIncident;
            }

            string value = type.Trim();

            if (Enum.TryParse<IncidentType>(
                    value,
                    ignoreCase: true,
                    out var result))
            {
                return result;
            }

            Console.WriteLine(
                $"⚠️ Неизвестный IncidentType '{value}'. " +
                "Используется OtherIncident."
            );

            return IncidentType.OtherIncident;
        }

        private static ServiceType ParseServiceType(string? service)
        {
            if (string.IsNullOrWhiteSpace(service))
                return ServiceType.MCHS;

            string value = service.Trim();

            if (Enum.TryParse<ServiceType>(
                    value,
                    ignoreCase: true,
                    out var result))
            {
                return result;
            }

            Console.WriteLine(
                $"⚠️ Неизвестная служба '{value}'. " +
                "Используется MCHS."
            );

            return ServiceType.MCHS;
        }

        private static ClassifierTag ParseClassifierTag(string? tag)
        {
            if (string.IsNullOrWhiteSpace(tag))
                return ClassifierTag.None;

            string value = tag.Trim();

            if (Enum.TryParse<ClassifierTag>(
                    value,
                    ignoreCase: true,
                    out var result))
            {
                return result;
            }

            Console.WriteLine(
                $"⚠️ Неизвестный ClassifierTag '{value}'. " +
                "Тег будет проигнорирован."
            );

            return ClassifierTag.None;
        }
    }
}