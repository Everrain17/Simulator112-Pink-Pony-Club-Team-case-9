using System;
using System.Collections.Generic;
using System.Linq;
using SimCore.Entities;
using SimCore.Enums;

namespace SimCore.Engine
{
    public static class TeacherEngine
    {
        public static (Incident Incident, ActiveCall ActiveCall) InjectCall(
            IncidentType type,
            int severity,
            int initialPanic,
            List<ServiceType> requiredServices,
            string description,
            string address,
            double lat,
            double lon,
            string? customUtterance,
            string? teacherComment,
            List<ClassifierTag> criticalTags,
            List<ClassifierTag> optionalTags,
            string? ekpCode,
            string? ekpName,
            Random rng,
            double totalElapsedSeconds,
            List<Incident> allIncidents,
            List<ActiveCall> activeCalls,
            List<string> systemEventsLog,
            double slaTimeSeconds,
            double endCallTimeSeconds,
            Func<int> nextCallNumber,
            Action resetIdleTimers)
        {
            int callNumber = nextCallNumber();
            int elapsedSeconds = (int)totalElapsedSeconds;
            string idSuffix = Guid.NewGuid().ToString("N");
            string incidentId = $"INC-INJ-{callNumber:D4}-{idSuffix}";
            string callId = $"CALL-{callNumber:D4}-{idSuffix}";

            var uniqueServices = requiredServices
                .Distinct()
                .ToList();
            var uniqueCriticalTags = criticalTags
                .Distinct()
                .ToList();
            var uniqueOptionalTags = optionalTags
                .Distinct()
                .ToList();

            var groundTruth = new IncidentGroundTruth(
                CallId: callId,
                IncidentId: incidentId,
                ExpectedIncidentType: type,
                CriticalTags: uniqueCriticalTags,
                OptionalTags: uniqueOptionalTags,
                RequiredServices: uniqueServices,
                Address: address
            );

            var incident = new Incident(
                Id: incidentId,
                Type: type,
                State: IncidentState.New,
                Address: address,
                Lat: lat,
                Lon: lon,
                Severity: severity,
                TimeElapsedSeconds: 0.0,
                RequiredServices: uniqueServices,
                Description: description,
                NaturalEscalationIntervalSeconds: 30,
                CriticalThreshold: Math.Max(8, severity + 1),
                EkpCode: ekpCode,
                EkpName: ekpName,
                GroundTruth: groundTruth
            );

            string openingLine = string.IsNullOrWhiteSpace(customUtterance)
                ? $"Срочно! {description}"
                : customUtterance;
            double speedModifier = 1.0 + (initialPanic / 100.0);
            CallerEmotion emotion = OperatorAuditEngine.GetEmotionFromPanic(initialPanic);

            var caller = new CallerState(
                Id: $"CALLER-INJ-{rng.Next(10000000, 99999999)}",
                CurrentEmotion: emotion,
                PanicLevel: initialPanic,
                Cooperativeness: Math.Max(0.1, 1.0 - (initialPanic / 150.0)),
                LastUtterance: openingLine,
                HasGivenAddress: false,
                HasGivenVictimsInfo: false,
                HasHungUp: false,
                SpeedModifier: speedModifier
            );

            var activeCall = new ActiveCall(
                Id: callId,
                IncidentId: incident.Id,
                TimeToConfirmSeconds: slaTimeSeconds,
                TimeRemainingSeconds: endCallTimeSeconds,
                SilenceDurationSeconds: 0.0,
                Caller: caller,
                StudentId: null,
                TeacherComment: teacherComment,
                CardState: CardState.Draft,
                CallStartedAtGlobalSeconds: totalElapsedSeconds
            );

            resetIdleTimers?.Invoke();
            allIncidents.Add(incident);
            activeCalls.Add(activeCall);
            systemEventsLog.Add($"[{elapsedSeconds}s] 🚨 [ИНЪЕКЦИЯ] Новый инцидент: {incident.Type} по адресу {incident.Address}");
            systemEventsLog.Add($"[{elapsedSeconds}s] 📞 Звонок {activeCall.Id}: \"{caller.LastUtterance}\" (Паника: {caller.PanicLevel}%)");

            return (incident, activeCall);
        }

        public static bool UpdateTeacherComment(
            string callId,
            string comment,
            List<ActiveCall> activeCalls,
            List<string> systemEventsLog,
            double totalElapsedSeconds)
        {
            int callIndex = activeCalls.FindIndex(c => c.Id == callId);
            if (callIndex < 0) return false;
            var call = activeCalls[callIndex];
            activeCalls[callIndex] = call with { TeacherComment = comment };
            systemEventsLog.Add($"[{(int)totalElapsedSeconds}s] 👨‍🏫 ВМЕШАТЕЛЬСТВО: Преподаватель скорректировал звонок {callId}. Инструкция: {comment}");
            return true;
        }
    }
}
