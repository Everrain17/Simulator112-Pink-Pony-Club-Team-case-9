using SimCore.Data;
using SimCore.Entities;
using SimCore.Enums;
using SimCore.Interfaces;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
namespace SimCore.Engine
{
    public record WorldState(
        int ElapsedSeconds,
        int ElapsedTicks,
        List<ActiveCall> ActiveCalls,
        List<Incident> AllIncidents,
        List<string> OperatorActionsLog,
        List<string> SystemEventsLog
    );
    public class SimulationEngine
    {
        private double _totalElapsedSeconds = 0;
        private int _callCounter = 0;
        private readonly int _callAnswerTimeSeconds;
        private readonly int _slaTimeSeconds;
        private readonly int _endCallTimeSeconds;
        private readonly int _seed;
        private readonly DdsProfile _activeProfile;
        private readonly List<ActiveCall> _activeCalls = new();
        private readonly List<Incident> _allIncidents = new();
        private readonly List<string> _operatorActionsLog = new();
        private readonly List<string> _systemEventsLog = new();
        private readonly IncidentGenerator _incidentGenerator;
        private readonly Random _rng;
        private readonly Dictionary<string, CallSession> _activeSessions = new();
        private readonly Dictionary<string, CallAnalysisResult> _callAnalysisResults = new();
        private readonly Dictionary<string, ActiveStudent> _activeStudents = new();
        private readonly EvaluationCriteria _criteria;
        private readonly List<IncidentProfile> _classifier = new();
        public int GetNextCallNumber()
        {
            _callCounter++;
            return _callCounter;
        }

        public void SetCallCounter(int lastNumber)
        {
            if (lastNumber > _callCounter)
            {
                _callCounter = lastNumber;
                Console.WriteLine($"⚙️ Счетчик ID звонков в ядре C# сдвинут на: {_callCounter}");
            }
        }
        private CallSession? GetSession(string callId)
        {
            _activeSessions.TryGetValue(callId, out var session);
            return session;
        }
        public SimulationEngine(
            List<StreetWithHouses> addresses,
            Random rng,
            DdsProfile profile = DdsProfile.Universal_112,
            int callAnswerTimeSeconds = 30,
            int slaTimeSeconds = 75,
            int endCallTimeSeconds = 420,
            int seed = 0,
            EvaluationCriteria criteria = null)
        {
            _rng = rng;
            _activeProfile = profile;
            _callAnswerTimeSeconds = callAnswerTimeSeconds;
            _slaTimeSeconds = slaTimeSeconds;
            _endCallTimeSeconds = endCallTimeSeconds;
            _seed = seed;
            _criteria = criteria ?? new EvaluationCriteria();
            _classifier = ClassifierLoader.LoadClassifier();
            _incidentGenerator = new IncidentGenerator(addresses, rng, profile, incidentProbability: 0.15, _classifier);
        }
        public Random GetRng() => _rng;
        public double GetTotalElapsedSeconds() => _totalElapsedSeconds;
        public double GetSlaTimeSeconds() => _slaTimeSeconds;
        public double GetEndCallTimeSeconds() => _endCallTimeSeconds;
        public List<ActiveCall> GetActiveCalls() => _activeCalls;
        public List<Incident> GetAllIncidents() => _allIncidents;
        public List<string> GetSystemEventsLog() => _systemEventsLog;
        public Dictionary<string, CallSession> GetActiveSessions() => _activeSessions;
        public Dictionary<string, CallAnalysisResult> GetCallAnalysisResults() => _callAnalysisResults;
        public List<IncidentProfile> GetClassifier() => _classifier.ToList();
        public WorldState GetCurrentState()
        {
            return new WorldState(
                (int)_totalElapsedSeconds,
                (int)(_totalElapsedSeconds / 5),
                _activeCalls.ToList(),
                _allIncidents.ToList(),
                _operatorActionsLog.ToList(),
                _systemEventsLog.ToList()
            );
        }
        public WorldState Update(double deltaTime)
        {
            _totalElapsedSeconds += deltaTime;
            int elapsedSecondsInt = (int)_totalElapsedSeconds;
            if (_activeCalls.Count < 25 && elapsedSecondsInt > 0 && elapsedSecondsInt % 15 == 0)
            {
                string targetIncidentId = $"INC-{elapsedSecondsInt:D4}";
                if (!_allIncidents.Any(i => i.Id == targetIncidentId))
                {
                    var newIncident = _incidentGenerator.TryGenerateIncident(elapsedSecondsInt);
                    if (newIncident.HasValue)
                    {
                        var (incident, caller) = newIncident.Value;
                        _allIncidents.Add(incident);
                        int callNumber = GetNextCallNumber();
                        var activeCall = new ActiveCall(
                            Id: $"CALL-{callNumber:D4}-{Guid.NewGuid():N}",
                            IncidentId: incident.Id,
                            TimeToConfirmSeconds: _slaTimeSeconds,
                            TimeRemainingSeconds: _endCallTimeSeconds,
                            SilenceDurationSeconds: 0.0,
                            Caller: caller,
                            StudentId: null,
                            CardState: CardState.Draft,
                            CallStartedAtGlobalSeconds: _totalElapsedSeconds
                        );
                        _activeCalls.Add(activeCall);
                        ResetIdleTimersForFreeStudents();
                        _systemEventsLog.Add($"[{elapsedSecondsInt}s] 🚨 Новый инцидент класс [{incident.Type}] по адресу {incident.Address}");
                        _systemEventsLog.Add($"[{elapsedSecondsInt}s] 📞 Звонок {activeCall.Id}: \"{caller.LastUtterance}\" (Паника: {caller.PanicLevel}%)");
                    }
                }
            }
            UpdateActiveCalls(deltaTime, elapsedSecondsInt);
            CheckStudentCallAcceptTimeouts(elapsedSecondsInt);
            UpdateIncidents(deltaTime, elapsedSecondsInt);
            return GetCurrentState();
        }
        private void UpdateActiveCalls(double deltaTime, int elapsedSeconds)
        {
            for (int i = _activeCalls.Count - 1; i >= 0; i--)
            {
                var call = _activeCalls[i];
                call = call with { TimeRemainingSeconds = call.TimeRemainingSeconds - deltaTime };
                bool operatorResponded = _operatorActionsLog.Any(a =>
                    a.Contains($"[{elapsedSeconds}s]") ||
                    a.Contains($"[{elapsedSeconds - 1}s]") ||
                    a.Contains($"[{elapsedSeconds - 2}s]"));
                if (!operatorResponded)
                {
                    call = call with { SilenceDurationSeconds = call.SilenceDurationSeconds + deltaTime };
                }
                else
                {
                    call = call with { SilenceDurationSeconds = 0.0 };
                }
                if (call.CardState == CardState.Draft)
                {
                    call = call with { TimeToConfirmSeconds = Math.Max(0, call.TimeToConfirmSeconds - deltaTime) };
                    if (call.TimeToConfirmSeconds <= 0 && !call.HasSLAViolationLogged)
                    {
                        _systemEventsLog.Add($"[{elapsedSeconds}s] ⚠️ НАРУШЕНИЕ SLA: Карточка {call.Id} не отправлена за {_slaTimeSeconds} секунд!");
                        if (_activeSessions.TryGetValue(call.Id, out var session))
                        {
                            lock (session)
                            {
                                if (!session.Violations.Any(v => v.Type == "CARD_FILL_TIMEOUT"))
                                {
                                    var violation = new ViolationRecord(
                                        "CARD_FILL_TIMEOUT",
                                        $"Превышено время заполнения и отправки карточки (лимит: {_slaTimeSeconds} сек).",
                                        DateTime.UtcNow
                                    );
                                    session.Violations.Add(violation);
                                    OperatorAuditEngine.AddViolationToAnalysis(call.Id, violation, _callAnalysisResults);
                                }
                            }
                        }
                        call = call with { HasSLAViolationLogged = true };
                    }
                }
                if (call.SilenceDurationSeconds >= 10.0)
                {
                    int oldPanic = call.Caller.PanicLevel;
                    double panicGrowth = deltaTime * 1.5 * call.Caller.SpeedModifier;
                    int newPanic = Math.Min(100, oldPanic + (int)panicGrowth);
                    if (newPanic != oldPanic && newPanic % 10 == 0)
                    {
                        string panicText = newPanic switch
                        {
                            < 50 => "нервничает",
                            < 70 => "паникует",
                            < 85 => "в истерике",
                            _ => "КРИТИЧЕСКАЯ ПАНИКА"
                        };
                        _systemEventsLog.Add($"[{elapsedSeconds}s] 😰 {call.Id}: Паника {oldPanic}% → {newPanic}% (молчание, звонящий {panicText})");
                    }
                    call = call with
                    {
                        Caller = call.Caller with
                        {
                            PanicLevel = newPanic,
                            CurrentEmotion = OperatorAuditEngine.GetEmotionFromPanic(newPanic),
                            Cooperativeness = Math.Max(0.2, call.Caller.Cooperativeness - (deltaTime * 0.01))
                        }
                    };
                }
                _activeCalls[i] = call;
            }
        }
        public void UpdateCardState(string callId, CardState newState)
        {
            int callIndex = _activeCalls.FindIndex(c => c.Id == callId);
            if (callIndex == -1) return;
            var call = _activeCalls[callIndex];
            _activeCalls[callIndex] = call with { CardState = newState, TimeToConfirmSeconds = 0 };
            _systemEventsLog.Add($"[{(int)_totalElapsedSeconds}s] ✅ Статус карточки {callId} изменен: {call.CardState} → {newState}");
        }
        private void UpdateIncidents(double deltaTime, int elapsedSeconds)
        {
            for (int i = 0; i < _allIncidents.Count; i++)
            {
                var incident = _allIncidents[i];
                if (incident.State == IncidentState.Resolved) continue;
                var updated = incident with { TimeElapsedSeconds = incident.TimeElapsedSeconds + deltaTime };
                int currentElapsedInt = (int)updated.TimeElapsedSeconds;
                if (currentElapsedInt > 0 &&
                    currentElapsedInt % incident.NaturalEscalationIntervalSeconds == 0 &&
                    (int)incident.TimeElapsedSeconds != currentElapsedInt)
                {
                    int oldSeverity = incident.Severity;
                    updated = updated with { Severity = incident.Severity + 1 };
                    if (updated.Severity >= incident.CriticalThreshold && incident.State != IncidentState.Critical)
                    {
                        updated = updated with { State = IncidentState.Critical };
                        _systemEventsLog.Add($"[{elapsedSeconds}s] 💥 Инцидент {incident.Id} КРИТИЧЕСКИЙ! Тяжесть {oldSeverity} → {updated.Severity}");
                    }
                    else if (incident.State == IncidentState.New)
                    {
                        updated = updated with { State = IncidentState.Escalating };
                        _systemEventsLog.Add($"[{elapsedSeconds}s] 📈 Инцидент {incident.Id} эскалирует: Тяжесть {oldSeverity} → {updated.Severity}");
                    }
                }
                _allIncidents[i] = updated;
            }
        }
        private void CheckStudentCallAcceptTimeouts(int elapsedSeconds)
        {
            foreach (var kvp in _activeStudents.ToList())
            {
                var student = kvp.Value;
                if (student.CurrentCallId != null) continue;
                if (student.IdleSince == null)
                {
                    _activeStudents[kvp.Key] = student with { IdleSince = _totalElapsedSeconds };
                    continue;
                }
                double idleTime = _totalElapsedSeconds - student.IdleSince.Value;
                if (idleTime > _callAnswerTimeSeconds &&
                    !student.HasCallAcceptViolationLogged &&
                    _activeCalls.Any(c => c.StudentId == null))
                {
                    var oldestFreeCall = _activeCalls
                        .Where(c => c.StudentId == null)
                        .OrderBy(c => c.CallStartedAtGlobalSeconds)
                        .FirstOrDefault();
                    if (oldestFreeCall != null)
                    {
                        var violation = new ViolationRecord(
                            "CALL_ACCEPT_TIMEOUT",
                            $"Студент бездействовал {idleTime:F0} сек и не принял доступный звонок {oldestFreeCall.Id}.",
                            DateTime.UtcNow
                        );
                        var updatedStudent = student with
                        {
                            Violations = new List<ViolationRecord>(student.Violations) { violation },
                            HasCallAcceptViolationLogged = true
                        };
                        _activeStudents[kvp.Key] = updatedStudent;
                        _systemEventsLog.Add($"[{elapsedSeconds}s] ⚠️ НАРУШЕНИЕ СТУДЕНТА: {kvp.Key} проигнорировал звонок {oldestFreeCall.Id} (простой > {_callAnswerTimeSeconds} сек)");
                    }
                }
            }
        }
        public void TriggerResetIdleTimers()
        {
            ResetIdleTimersForFreeStudents();
        }
        private void ResetIdleTimersForFreeStudents()
        {
            foreach (var kvp in _activeStudents.ToList())
            {
                if (kvp.Value.CurrentCallId == null)
                {
                    _activeStudents[kvp.Key] = kvp.Value with
                    {
                        IdleSince = _totalElapsedSeconds,
                        HasCallAcceptViolationLogged = false
                    };
                }
            }
        }
        public void RegisterAction(string actionDescription)
        {
            _operatorActionsLog.Add($"[{(int)_totalElapsedSeconds}s] {actionDescription}");
            _systemEventsLog.Add($"[{(int)_totalElapsedSeconds}s] ✅ {actionDescription}");
        }
        public bool AssignStudentToCall(string callId, string studentId)
        {
            int callIndex = _activeCalls.FindIndex(c => c.Id == callId);
            if (callIndex < 0) return false;
            var call = _activeCalls[callIndex];
            if (call.StudentId != null && call.StudentId != studentId) return false;
            _activeCalls[callIndex] = call with { StudentId = studentId };
            if (!_activeStudents.TryGetValue(studentId, out var student))
            {
                student = new ActiveStudent(studentId);
                _activeStudents[studentId] = student;
            }

            _activeStudents[studentId] = student with
            {
                CurrentCallId = callId,
                IdleSince = null,
                HasCallAcceptViolationLogged = false
            };

            if (!_activeSessions.ContainsKey(callId))
            {
                var session = new CallSession
                {
                    CallId = callId
                };

                session.Utterances.Add(
                    new Utterance
                    {
                        Speaker = SpeakerRole.Caller,
                        Text = call.Caller.LastUtterance,
                        Timestamp = DateTime.UtcNow
                    }
                );

                _activeSessions[callId] = session;
            }
            _systemEventsLog.Add($"[{(int)_totalElapsedSeconds}s] ✅ Студент {studentId} принял звонок {callId}");
            return true;
        }

        public bool ReleaseStudentFromCallSync(string callId)
        {
            int callIndex = _activeCalls.FindIndex(
                c => c.Id == callId
            );

            if (callIndex < 0)
                return false;

            var call = _activeCalls[callIndex];

            if (!string.IsNullOrEmpty(call.StudentId) &&
                _activeStudents.TryGetValue(
                    call.StudentId,
                    out var student))
            {
                _activeStudents[call.StudentId] =
                    student with
                    {
                        CurrentCallId = null,
                        IdleSince = _totalElapsedSeconds,
                        HasCallAcceptViolationLogged = false
                    };
            }

            _activeCalls[callIndex] =
                call with
                {
                    StudentId = null,
                    TimeToConfirmSeconds = _slaTimeSeconds,
                    HasSLAViolationLogged = false
                };

            _systemEventsLog.Add(
                $"[{(int)_totalElapsedSeconds}s] " +
                $"Студент освобождён от звонка {callId}. " +
                $"Звонок возвращён в очередь."
            );

            return true;
        }

        public bool CompleteCallSync(string callId)
        {
            int callIndex = _activeCalls.FindIndex(
                c => c.Id == callId
            );

            if (callIndex < 0)
                return false;

            var call = _activeCalls[callIndex];

            if (!string.IsNullOrEmpty(call.StudentId) &&
                _activeStudents.TryGetValue(
                    call.StudentId,
                    out var student))
            {
                _activeStudents[call.StudentId] = student with
                {
                    CurrentCallId = null,
                    IdleSince = _totalElapsedSeconds,
                    HasCallAcceptViolationLogged = false
                };
            }

            _activeCalls.RemoveAt(callIndex);

            int incidentIndex = _allIncidents.FindIndex(
                i => i.Id == call.IncidentId
            );

            if (incidentIndex >= 0)
            {
                _allIncidents[incidentIndex] =
                    _allIncidents[incidentIndex] with
                    {
                        State = IncidentState.Resolved
                    };
            }

            _systemEventsLog.Add(
                $"[{(int)_totalElapsedSeconds}s] " +
                $"✅ Звонок {callId} окончательно закрыт в ядре."
            );

            return true;
        }

        public object? GetCallSnapshot(string callId)
        {
            var call = _activeCalls.FirstOrDefault(
                c => c.Id == callId
            );

            if (call == null)
                return null;

            var incident = _allIncidents.FirstOrDefault(
                i => i.Id == call.IncidentId
            );

            _callAnalysisResults.TryGetValue(
                callId,
                out var analysis
            );

            var groundTruth =
                incident?.GroundTruth != null
                    ? incident.GroundTruth with
                    {
                        CallId = callId
                    }
                    : null;

            object? dialogue = null;

            if (_activeSessions.TryGetValue(callId, out var session))
            {
                lock (session)
                {
                    dialogue = new
                    {
                        callId = session.CallId,
                        emotionalLevel = session.EmotionalLevel,

                        utterances = session.Utterances
                            .Select(x => new
                            {
                                id = x.Id,
                                speaker = x.Speaker.ToString(),
                                text = x.Text,
                                timestamp = x.Timestamp
                            })
                            .ToList(),

                        violations = session.Violations
                            .Select(x => new
                            {
                                type = x.Type,
                                description = x.Description,
                                timestamp = x.Timestamp
                            })
                            .ToList()
                    };
                }
            }

            return new
            {
                callId = callId,
                incidentId = call.IncidentId,

                call = call,
                incident = incident,
                groundTruth = groundTruth,

                analysis = analysis,

                dialogue = dialogue,

                elapsedSeconds = _totalElapsedSeconds
            };
        }
    }
}
