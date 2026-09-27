using System;
using System.Collections.Generic;
using System.Linq;
using SimCore.Entities;
using SimCore.Enums;

namespace SimCore.Engine
{
    public static class OperatorAuditEngine
    {
        // 1. Проверка тайм-аутов молчания
        public static string? CheckForSpeechTimeouts(string callId, double continuousSilence, double maxAllowedSilenceSeconds)
        {
            if (continuousSilence > maxAllowedSilenceSeconds)
            {
                return $"Превышен лимит молчания оператора: {continuousSilence:F1} сек (максимум {maxAllowedSilenceSeconds} сек).";
            }
            return null;
        }

        // 2. Проверка многословия оператора
        public static string? CheckForOperatorLoquacity(string callId, int wordCount, int maxWordsPerUtterance)
        {
            if (wordCount > maxWordsPerUtterance)
            {
                return $"Оператор слишком многословен ({wordCount} слов). Реплика должна быть краткой и по существу.";
            }
            return null;
        }

        // 3. Добавление нарушения в аналитическую карточку звонка
        public static void AddViolationToAnalysis(
            string callId,
            ViolationRecord violation,
            Dictionary<string, CallAnalysisResult> callAnalysisResults)
        {
            if (callAnalysisResults.TryGetValue(callId, out var state))
            {
                var newViolations = new List<ViolationRecord>(state.Violations) { violation };
                callAnalysisResults[callId] = state with { Violations = newViolations };
            }
        }

        // 4. Обновление текста последней реплики в сессии оперативной памяти
        public static void ForceUpdateLastUtterance(
            string callId,
            string text,
            Dictionary<string, CallSession> activeSessions)
        {
            if (activeSessions.TryGetValue(callId, out var session))
            {
                lock (session)
                {
                    var lastUtterance = session.Utterances.LastOrDefault();

                    if (lastUtterance == null ||
                        lastUtterance.Speaker != SpeakerRole.Operator)
                    {
                        session.Utterances.Add(
                            new Utterance
                            {
                                Speaker = SpeakerRole.Operator,
                                Text = text,
                                Timestamp = DateTime.UtcNow
                            }
                        );

                        return;
                    }

                    lastUtterance.Text = text;
                    lastUtterance.Timestamp = DateTime.UtcNow;
                }
            }
        }

        // 5. Проверка: можно ли перебить ИИ-бота в данный момент
        public static bool CanBotBeInterrupted(string callId, Dictionary<string, CallSession> activeSessions)
        {
            if (activeSessions.TryGetValue(callId, out var session))
            {
                if (session.EmotionalLevel > 80)
                {
                    return false;
                }
            }
            return true;
        }

        // 6. Математическая обработка ИИ-анализа реплики (Управление паникой и логами)
        public static void ApplyAnalysisResult(
            string callId,
            OperatorActionAnalysis analysis,
            double totalElapsedSeconds,
            List<ActiveCall> activeCalls,
            List<string> operatorActionsLog,
            List<string> systemEventsLog)
        {
            int elapsedSeconds = (int)totalElapsedSeconds;
            operatorActionsLog.Add($"[{elapsedSeconds}s] {analysis.Summary}");
            systemEventsLog.Add($"[{elapsedSeconds}s] ИИ-Анализ: {analysis.Summary}");

            int callIndex = activeCalls.FindIndex(c => c.Id == callId);
            if (callIndex == -1) return;

            var call = activeCalls[callIndex];
            var caller = call.Caller;

            // 1. Адрес выяснен -> меняем статус карточки
            if (analysis.AddressClarified && !caller.HasGivenAddress)
            {
                caller = caller with { HasGivenAddress = true };
                systemEventsLog.Add($"[{elapsedSeconds}s] 📍 Движок: Адрес инцидента успешно подтвержден в диалоге.");
            }

            // 2. Инструкция дана -> меняем статус и снижаем панику (психологический эффект)
            if (analysis.MedicalInstructionGiven && !caller.HasGivenVictimsInfo)
            {
                caller = caller with { HasGivenVictimsInfo = true };
                int newPanic = Math.Max(0, caller.PanicLevel - 15);
                caller = caller with { PanicLevel = newPanic };
                systemEventsLog.Add($"[{elapsedSeconds}s] 🩺 Движок: Инструкция первой помощи принята. Паника снижена на 15%.");
            }

            // 3. Службы вызваны -> снижаем панику (психологический эффект: "помощь уже едет")
            if (analysis.ServicesDispatched)
            {
                int newPanic = Math.Max(0, caller.PanicLevel - 20);
                caller = caller with { PanicLevel = newPanic };
                systemEventsLog.Add($"[{elapsedSeconds}s] 🚑 Движок: Заявитель уведомлен о выезде служб. Паника снижена на 20%.");
            }

            // 4. Оператор успокаивает -> плавное снижение паники
            if (analysis.IsCalmingOperator)
            {
                int newPanic = Math.Max(0, caller.PanicLevel - 10);
                caller = caller with { PanicLevel = newPanic };
            }

            // Сбрасываем таймер молчания, так как был диалог
            activeCalls[callIndex] = call with { Caller = caller, SilenceDurationSeconds = 0.0 };
        }

        // 7. Точечное обновление хронометража и состояния анализа по звонку
        public static void UpdateCallAnalysis(
            string callId,
            OperatorActionAnalysis analysis,
            double currentCallSeconds,
            Dictionary<string, CallAnalysisResult> callAnalysisResults)
        {
            if (!callAnalysisResults.TryGetValue(callId, out var state))
            {
                state = new CallAnalysisResult(
                    CallId: callId,
                    AddressClarified: false, AddressClarifiedAtSeconds: null,
                    VictimsInfoClarified: false, VictimsInfoClarifiedAtSeconds: null,
                    MedicalInstructionGiven: false, MedicalInstructionGivenAtSeconds: null,
                    IsCalmingOperator: false, IsCalmingOperatorAtSeconds: null,
                    ServicesDispatched: false, ServicesDispatchedAtSeconds: null,
                    CardSubmissionTimeSeconds: null,
                    Violations: new List<ViolationRecord>()
                );
            }

            var newAddress = state.AddressClarified || analysis.AddressClarified;
            var newAddressTime = newAddress && !state.AddressClarified ? currentCallSeconds : state.AddressClarifiedAtSeconds;

            var newVictims = state.VictimsInfoClarified || analysis.VictimsInfoClarified;
            var newVictimsTime = newVictims && !state.VictimsInfoClarified ? currentCallSeconds : state.VictimsInfoClarifiedAtSeconds;

            var newMedical = state.MedicalInstructionGiven || analysis.MedicalInstructionGiven;
            var newMedicalTime = newMedical && !state.MedicalInstructionGiven ? currentCallSeconds : state.MedicalInstructionGivenAtSeconds;

            var newCalming = state.IsCalmingOperator || analysis.IsCalmingOperator;
            var newCalmingTime = newCalming && !state.IsCalmingOperator ? currentCallSeconds : state.IsCalmingOperatorAtSeconds;

            var newServices = state.ServicesDispatched || analysis.ServicesDispatched;
            var newServicesTime = newServices && !state.ServicesDispatched ? currentCallSeconds : state.ServicesDispatchedAtSeconds;

            callAnalysisResults[callId] = state with
            {
                AddressClarified = newAddress,
                AddressClarifiedAtSeconds = newAddressTime,
                VictimsInfoClarified = newVictims,
                VictimsInfoClarifiedAtSeconds = newVictimsTime,
                MedicalInstructionGiven = newMedical,
                MedicalInstructionGivenAtSeconds = newMedicalTime,
                IsCalmingOperator = newCalming,
                IsCalmingOperatorAtSeconds = newCalmingTime,
                ServicesDispatched = newServices,
                ServicesDispatchedAtSeconds = newServicesTime
            };
        }
        public static CallerEmotion GetEmotionFromPanic(int panicLevel)
        {
            return panicLevel switch
            {
                < 30 => CallerEmotion.Calm,
                < 50 => CallerEmotion.Nervous,
                < 70 => CallerEmotion.Crying,
                < 85 => CallerEmotion.Panicking,
                _ => CallerEmotion.Hysterical
            };
        }
        public static object ExecuteSupplementCall(
    string callId,
    List<ServiceType> addedServices,
    double currentTimeSeconds,
    double slaTimeSeconds,
    List<ActiveCall> activeCalls,
    List<Incident> allIncidents,
    Dictionary<string, CallSession> activeSessions,
    Dictionary<string, CallAnalysisResult> callAnalysisResults)
        {
            int callIndex = activeCalls.FindIndex(c => c.Id == callId);
            if (callIndex < 0) return new { success = false, error = "Звонок не найден" };
            var call = activeCalls[callIndex];

            int incidentIndex = allIncidents.FindIndex(i => i.Id == call.IncidentId);
            if (incidentIndex < 0) return new { success = false, error = "Связанный инцидент не найден" };
            var incident = allIncidents[incidentIndex];

            bool isLate = currentTimeSeconds > slaTimeSeconds;
            if (isLate)
            {
                var violation = new ViolationRecord(
                    "LATE_SUPPLEMENT",
                    $"Дополнение карточки через {currentTimeSeconds:F0} сек (лимит: {slaTimeSeconds} сек). Службы уже отправлены.",
                    DateTime.UtcNow
                );
                if (activeSessions.TryGetValue(callId, out var session))
                {
                    lock (session)
                    {
                        if (!session.Violations.Any(v => v.Type == "LATE_SUPPLEMENT"))
                        {
                            session.Violations.Add(violation);
                            AddViolationToAnalysis(callId, violation, callAnalysisResults);
                        }
                    }
                }
                return new { success = true, warning = $"Дополнение принято, но выставлен штраф...", violation = violation };
            }

            // Мутируем данные прямо в переданной коллекции
            var updatedServices = incident.RequiredServices.Concat(addedServices).Distinct().ToList();
            allIncidents[incidentIndex] = incident with { RequiredServices = updatedServices };

            return new { success = true, message = "Службы добавлены без штрафа" };
        }
        // 9. Получить эталонные данные происшествия из вшитого ДНК инцидента (Полностью вынесено из ядра)
        public static IncidentGroundTruth? GetGroundTruth(string callId, List<ActiveCall> activeCalls, List<Incident> allIncidents)
        {
            var call = activeCalls.FirstOrDefault(c => c.Id == callId);
            if (call == null) return null;

            var incident = allIncidents.FirstOrDefault(i => i.Id == call.IncidentId);
            if (incident == null) return null;

            // Возвращаем вшитый эталон, просто подставляя туда ID звонка для контроллера API
            return incident.GroundTruth != null ? incident.GroundTruth with { CallId = call.Id } : null;
        }
    }
}
