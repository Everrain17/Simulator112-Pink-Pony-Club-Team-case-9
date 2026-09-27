using SimCore.Data;
using SimCore.Entities;
using SimCore.Enums;
using System;
using System.Collections.Generic;
using System.Linq;

namespace SimCore.Engine
{
    public class IncidentGenerator
    {
        private readonly List<StreetWithHouses> _addresses;
        private readonly Random _rng;
        private readonly double _incidentProbability;
        private readonly DdsProfile _activeProfile;
        private readonly List<IncidentProfile> _classifier;
        private int _lastIncidentGeneratedAt = -30;
        private readonly string spawnedGender =
            Random.Shared.NextDouble() < 0.5
                ? "male"
                : "female";

        public IncidentGenerator(
            List<StreetWithHouses> addresses,
            Random rng,
            DdsProfile profile,
            double incidentProbability,
            List<IncidentProfile> classifier)
        {
            _addresses =
                addresses ??
                throw new ArgumentNullException(nameof(addresses));

            _rng =
                rng ??
                throw new ArgumentNullException(nameof(rng));

            _activeProfile = profile;
            _incidentProbability = incidentProbability;

            _classifier =
                classifier ??
                new List<IncidentProfile>();
        }

        public (Incident, CallerState)? TryGenerateIncident(
            int elapsedSeconds)
        {
            // Не чаще одного нового происшествия каждые 30 секунд
            if (elapsedSeconds - _lastIncidentGeneratedAt < 30)
                return null;

            // Вероятность возникновения происшествия
            if (_rng.NextDouble() > _incidentProbability)
                return null;

            // Нет загруженного классификатора
            if (_classifier.Count == 0)
                return null;

            // Выбираем случайный профиль
            var profile =
                _classifier[_rng.Next(_classifier.Count)];

            // Проверяем адреса
            if (_addresses.Count == 0)
                return null;

            var street =
                _addresses[_rng.Next(_addresses.Count)];

            if (street.Houses.Count == 0)
                return null;

            var house =
                street.Houses[
                    _rng.Next(street.Houses.Count)
                ];

            string fullAddress =
                $"{street.Name}, {house.Number}";

            // ---------------------------------------------------------
            // СЛУЖБЫ
            // ---------------------------------------------------------

            var servicesList =
                new List<ServiceType>
                {
                    profile.MainService
                };

            servicesList.AddRange(
                profile.AdditionalServices
                    .Where(service =>
                        !servicesList.Contains(service))
            );

            // ---------------------------------------------------------
            // TAGS
            // ---------------------------------------------------------

            ClassifierTag combinedTags =
                ClassifierTag.None;

            var criticalTags =
                new List<ClassifierTag>();

            var optionalTags =
                new List<ClassifierTag>();

            foreach (var tag in profile.CriticalTags)
            {
                if (tag == ClassifierTag.None)
                    continue;

                combinedTags |= tag;

                if (TagMetadata.IsCritical(tag))
                {
                    criticalTags.Add(tag);
                }
                else
                {
                    optionalTags.Add(tag);
                }
            }

            // ---------------------------------------------------------
            // SEVERITY
            // ---------------------------------------------------------

            int severity =
                _rng.Next(4, 8);

            if (servicesList.Count >= 3)
            {
                severity += 2;
            }

            // ---------------------------------------------------------
            // ID
            // ---------------------------------------------------------

            string incidentId =
                $"INC-{elapsedSeconds:D4}";

            // ---------------------------------------------------------
            // HIDDEN FACTS
            // ---------------------------------------------------------

            int stableSeed =
                _rng.Next() +
                incidentId.GetHashCode();

            var localRng =
                new Random(stableSeed);

            string age =
                localRng.Next(18, 75) + " лет";

            string who =
                localRng.Next(0, 2) == 0
                    ? "прохожий / очевидец"
                    : "сосед / пострадавший";

            var hiddenFacts =
                new HiddenScenarioFacts(
                    Address: fullAddress,

                    VictimAge: age,

                    Symptoms:
                        profile.IncidentType
                            .GetSymptomsDescription(),

                    WhoIsCalling: who,

                    Gender: spawnedGender
                );

            // ---------------------------------------------------------
            // GROUND TRUTH
            // ---------------------------------------------------------

            var groundTruth =
                new IncidentGroundTruth(
                    CallId: "",

                    IncidentId: incidentId,

                    ExpectedIncidentType:
                        profile.IncidentType,

                    CriticalTags:
                        criticalTags,

                    OptionalTags:
                        optionalTags,

                    RequiredServices:
                        servicesList,

                    Address:
                        fullAddress
                );

            // ---------------------------------------------------------
            // СЦЕНАРИЙ
            // ---------------------------------------------------------

            string targetScenario =
                !string.IsNullOrWhiteSpace(
                    profile.ScenarioDescription)
                &&
                profile.ScenarioDescription !=
                    "Описание сценария отсутствует"

                    ? profile.ScenarioDescription

                    : profile.IncidentType
                        .GetGeneralDescription();

            // ---------------------------------------------------------
            // INCIDENT
            // ---------------------------------------------------------

            var incident =
                new Incident(
                    Id:
                        incidentId,

                    Type:
                        profile.IncidentType,

                    State:
                        IncidentState.New,

                    Address:
                        fullAddress,

                    Lat:
                        house.Lat,

                    Lon:
                        house.Lon,

                    Severity:
                        severity,

                    TimeElapsedSeconds:
                        0.0,

                    RequiredServices:
                        servicesList,

                    Description:
                        $"{profile.Name} | {targetScenario}",

                    NaturalEscalationIntervalSeconds:
                        _rng.Next(35, 55),

                    CriticalThreshold:
                        _rng.Next(8, 10),

                    Tags:
                        combinedTags,

                    TargetProfile:
                        _activeProfile,

                    EkpCode:
                        profile.EkpCode,

                    EkpName:
                        profile.Name,

                    ScenarioDescription:
                        targetScenario,

                    HiddenFacts:
                        hiddenFacts,

                    GroundTruth:
                        groundTruth
                );

            // ---------------------------------------------------------
            // CALLER
            // ---------------------------------------------------------

            var caller =
                GenerateCallerState(
                    profile,
                    severity
                );
            _lastIncidentGeneratedAt = elapsedSeconds;
            return (incident, caller);
        }

        private string GenerateRussianPhone()
        {
            return
                $"+7 (9{_rng.Next(0, 10)}{_rng.Next(0, 10)}) " +
                $"{_rng.Next(100, 1000)}-" +
                $"{_rng.Next(10, 100)}-" +
                $"{_rng.Next(10, 100)}";
        }

        private CallerState GenerateCallerState(
            IncidentProfile profile,
            int severity)
        {
            // ---------------------------------------------------------
            // УРОВЕНЬ ПАНИКИ
            // ---------------------------------------------------------

            int panicLevel = 50;

            bool hasExplosionRisk =
                profile.CriticalTags.Contains(
                    ClassifierTag.ExplosionRisk);

            bool hasCasualties =
                profile.CriticalTags.Contains(
                    ClassifierTag.Casualties);

            bool hasChildrenAtRisk =
                profile.CriticalTags.Contains(
                    ClassifierTag.ChildrenAtRisk);

            bool hasTrafficAccident =
                profile.CriticalTags.Contains(
                    ClassifierTag.TrafficAccident);

            bool hasGasLeak =
                profile.CriticalTags.Contains(
                    ClassifierTag.GasLeak);

            bool hasCollapse =
                profile.CriticalTags.Contains(
                    ClassifierTag.Collapse);

            bool hasCriticalCondition =
                profile.CriticalTags.Contains(
                    ClassifierTag.CriticalCondition);

            bool hasPeopleTrapped =
                profile.CriticalTags.Contains(
                    ClassifierTag.PeopleTrapped);

            // Самые критичные ситуации
            if (
                hasExplosionRisk
                ||
                profile.IncidentType ==
                    IncidentType.Explosion
                ||
                profile.IncidentType ==
                    IncidentType.ExplosionOrTerroristThreat
                ||
                profile.IncidentType ==
                    IncidentType.UAV &&
                hasExplosionRisk
            )
            {
                panicLevel = 85;
            }
            // Несколько людей / дети / критическое состояние
            else if (
                hasChildrenAtRisk
                ||
                hasCasualties
                ||
                hasCriticalCondition
                ||
                hasPeopleTrapped
            )
            {
                panicLevel = 80;
            }
            // Обрушение / газ / радиационная опасность
            else if (
                hasCollapse
                ||
                profile.IncidentType ==
                    IncidentType.Collapse
                ||
                profile.IncidentType ==
                    IncidentType.CollapseThreat
            )
            {
                panicLevel = 75;
            }
            else if (
                hasGasLeak
                ||
                profile.IncidentType ==
                    IncidentType.HazardousSubstanceOrRadiationThreat
                ||
                profile.IncidentType ==
                    IncidentType.Radiation
            )
            {
                panicLevel = 70;
            }
            // ДТП
            else if (
                hasTrafficAccident
                ||
                profile.IncidentType ==
                    IncidentType.TrafficAccident
            )
            {
                panicLevel = 70;
            }
            // Человек в опасности
            else if (
                profile.IncidentType ==
                    IncidentType.PersonInDanger
                ||
                profile.IncidentType ==
                    IncidentType.ChildInDanger
            )
            {
                panicLevel = 70;
            }

            // ---------------------------------------------------------
            // ПЕРСОНА ЗВОНИВШЕГО
            // ---------------------------------------------------------

            CallerPersona persona =
                _rng.NextDouble() switch
                {
                    < 0.20 =>
                        CallerPersona.ElderlyNeighbor,

                    < 0.35 =>
                        CallerPersona.PanickedParent,

                    < 0.50 =>
                        CallerPersona.ProfessionalWorker,

                    < 0.65 =>
                        CallerPersona.IndifferentPasserby,

                    < 0.80 =>
                        CallerPersona.AggressiveResident,

                    < 0.90 =>
                        CallerPersona.DrunkPerson,

                    < 0.98 =>
                        CallerPersona.Child,

                    _ =>
                        CallerPersona.ElderlyNeighbor
                };

            // ---------------------------------------------------------
            // ПЕРВАЯ ФРАЗА
            // ---------------------------------------------------------

            string rawTrigger =
                panicLevel > 75
                    ? "Алло, срочно помогите!"
                    : panicLevel > 50
                        ? "Алло, 112?"
                        : "Здравствуйте, у нас тут проблема.";

            // ---------------------------------------------------------
            // CALLER STATE
            // ---------------------------------------------------------

            return new CallerState(
                Id:
                    $"CALLER-{_rng.Next(10000000, 99999999)}",

                CurrentEmotion:
                    OperatorAuditEngine
                        .GetEmotionFromPanic(
                            panicLevel),

                PanicLevel:
                    panicLevel,

                Cooperativeness:
                    Math.Max(
                        0.1,
                        1.0 -
                        (panicLevel / 150.0)
                    ),

                LastUtterance:
                    rawTrigger,

                HasGivenAddress:
                    false,

                HasGivenVictimsInfo:
                    false,

                HasHungUp:
                    false,

                SpeedModifier:
                    1.0 +
                    (panicLevel / 100.0),

                Persona:
                    persona,

                PhoneNumber:
                    GenerateRussianPhone()
            );
        }
    }
}