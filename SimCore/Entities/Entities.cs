using SimCore.Enums;
using System.Collections.Generic;
namespace SimCore.Entities
{
    public record Incident(
        string Id,
        IncidentType Type,
        IncidentState State,
        string Address,
        double Lat,
        double Lon,
        int Severity,
        double TimeElapsedSeconds,
        List<ServiceType> RequiredServices,
        string Description,
        int NaturalEscalationIntervalSeconds,
        int CriticalThreshold,
        ClassifierTag Tags = ClassifierTag.None,
        DdsProfile TargetProfile = DdsProfile.Universal_112,
        string? EkpCode = null,
        string? EkpName = null,
        string? ScenarioDescription = null,
        HiddenScenarioFacts? HiddenFacts = null,
        IncidentGroundTruth? GroundTruth = null
    );
    public record IncidentProfile(
        string EkpCode,
        string Name,
        string Subgroup,
        IncidentType IncidentType,
        ServiceType MainService,
        List<ServiceType> AdditionalServices,
        List<ClassifierTag> CriticalTags,
        string ScenarioDescription
    );
    public record IncidentProfileJson(
        string? EkpCode,
        string? Name,
        string? Subgroup,
        string? IncidentType,
        string? MainService,
        List<string>? AdditionalServices,
        List<string>? CriticalTags,
        string? ScenarioDescription
    );
    public record IncidentGroundTruth(
        string CallId,
        string IncidentId,
        IncidentType ExpectedIncidentType,
        List<ClassifierTag> CriticalTags,
        List<ClassifierTag> OptionalTags,
        List<ServiceType> RequiredServices,
        string Address
    );
    public record ChecklistResult(
    IncidentType IncidentType,
    Dictionary<string, string> Answers
);
    public record CallerState(
        string Id,
        CallerEmotion CurrentEmotion,
        int PanicLevel,
        double Cooperativeness,
        string LastUtterance,
        bool HasGivenAddress,
        bool HasGivenVictimsInfo,
        bool HasHungUp,
        double SpeedModifier,
        CallerPersona Persona = CallerPersona.ElderlyNeighbor,
        string? PhoneNumber = null
    );
    public record StreetWithHouses(
        string Name,
        string Type,
        List<HouseReference> Houses
    );
    public record HouseReference(
        string Number,
        double Lat,
        double Lon,
        string? BuildingType
    );
    public record HiddenScenarioFacts(string Address, string VictimAge, string Symptoms, string WhoIsCalling, string Gender);
    public record OperatorActionAnalysis(
        bool AddressClarified,
        bool VictimsInfoClarified,
        bool MedicalInstructionGiven,
        bool ServicesDispatched,
        bool IsCalmingOperator,
        string Summary
    );
    public record ServiceNotification(
        ServiceType Service,
        bool IsNotified,
        CardState Status = CardState.Draft,
        double ConfirmTimerSeconds = 30.0
    );
    public class CompleteCallRequest
    {
        public string CallId { get; set; } = string.Empty;
        public List<string>? ServiceCodes { get; set; }
        public string OperatorNotes { get; set; } = string.Empty;
        public string SelectedIncidentTypeCode { get; set; } = string.Empty;
        public Dictionary<string, string>? ChecklistAnswers { get; set; }
    }
    public class CallSession
    {
        public string CallId { get; set; } = string.Empty;
        public List<Utterance> Utterances { get; set; } = new();
        public List<ViolationRecord> Violations { get; set; } = new();
        public int EmotionalLevel { get; set; } = 50;
    }
    public record ViolationRecord(string Type, string Description, DateTime Timestamp);
    public record CompletedCallData(
        string CallId,
        string IncidentId,
        double StartTimeSeconds,
        double EndTimeSeconds,
        double TotalDurationSeconds,
        string StudentId,
        IncidentGroundTruth GroundTruth,
        CallAnalysisResult Analysis,
        List<ServiceType> DispatchedServices,
        DateTime CompletedAt,
        TextAnalysisResult? TextAnalysis,
        IncidentType SelectedIncidentType,
        ChecklistResult? Checklist = null
    );
    public record ActiveStudent(
        string StudentId,
        string? CurrentCallId = null,
        double? IdleSince = null,
        bool HasCallAcceptViolationLogged = false,
        List<ViolationRecord>? Violations = null
    )
    {
        public ActiveStudent(string studentId)
            : this(studentId, null, null, false, new List<ViolationRecord>()) { }
    }
    public record EvaluationCriteria(
    double MaxAllowedSilenceSeconds = 15.0,
    int MaxWordsPerUtterance = 40,
    int MinGrammarScore = 70,
    int MinFactualAccuracy = 70
    );
    public record ActiveCall(
        string Id,
        string IncidentId,
        CallerState Caller,
        string? StudentId = null,
        string? TeacherComment = null,
        CardState CardState = CardState.Draft,
        double TimeToConfirmSeconds = 30.0,
        double TimeRemainingSeconds = 180.0,
        double SilenceDurationSeconds = 0.0,
        bool HasSLAViolationLogged = false,
        double CallStartedAtGlobalSeconds = 0.0
    );
    public record AIPromptPayload(
        string Timestamp, string CallId, string IncidentId, int PanicLevel, string EmotionalTone,
        double SpeakingRate, string IncidentType, string ScenarioContext, string Description,
        bool HasGivenAddress, bool HasGivenVictimsInfo, string LastOperatorAction,
        HiddenScenarioFacts HiddenScenarioFacts, List<string> SuggestedTopics,
        int IncidentSeverity, bool IsCritical, string TextPrompt
    );
    public record CallAnalysisResult(
    string CallId,
    bool AddressClarified,
    double? AddressClarifiedAtSeconds,
    bool VictimsInfoClarified,
    double? VictimsInfoClarifiedAtSeconds,
    bool MedicalInstructionGiven,
    double? MedicalInstructionGivenAtSeconds,
    bool IsCalmingOperator,
    double? IsCalmingOperatorAtSeconds,
    bool ServicesDispatched,
    double? ServicesDispatchedAtSeconds,
    double? CardSubmissionTimeSeconds,
    List<ViolationRecord> Violations
    );
    public record TextAnalysisResult(
        int GrammarScore,
        int FactualAccuracy,
        List<string> MissingCriticalFacts,
        string AiComment,
        bool First100CharsCheck = true
    );
    public class Utterance
    {
        public string Id { get; set; } = Guid.NewGuid().ToString();
        public SpeakerRole Speaker { get; set; }
        public string Text { get; set; } = string.Empty;
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }
}
