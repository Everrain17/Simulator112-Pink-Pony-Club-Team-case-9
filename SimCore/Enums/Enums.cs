using System;
using System.Collections.Generic;
namespace SimCore.Enums
{
    public enum IncidentType
    {
        Service101,
        Service102,
        Service103,
        Service104,
        CityInfrastructureAccident,
        TransportObjectAccident,
        HydraulicStructureAccident,
        HazardousProductionAccident,
        ServiceThanks,
        UAV,
        Explosion,
        RoadObstruction,
        TrafficAccident,
        ComplaintAboutServices,
        Animals,
        Consultation,
        Collapse,
        AssistanceToServices,
        NaturalDisaster,
        OtherIncident,
        Radiation,
        BrokenThermometer,
        ChildInDanger,
        WaterAccumulation,
        FatalOutcome,
        SocialAssistance,
        Training,
        ExplosionOrTerroristThreat,
        HazardousSubstanceOrRadiationThreat,
        CollapseThreat,
        PersonInDanger,
        EnvironmentalIncident
    }
    public enum IncidentState
    {
        New,
        Escalating,
        Critical,
        Resolved
    }
    public enum CallerEmotion
    {
        Calm,
        Nervous,
        Crying,
        Panicking,
        Hysterical,
        Angry
    }
    public enum SpeakerRole
    {
        Operator,
        Caller
    }
    public enum ServiceType
    {
        MCHS,
        POLICE,
        AMBULANCE,
        GAS,
        ANTITERROR,
        MOSLIFT,
        DEPT_ZHKH,
        TSOMP,
        MOSVODOCANAL,
        ZODD,
        AUTOROADS,
        GORMOST,
        MOEK,
        MOESK,
        MGTS,
        METRO,
        MOSGORTRANS,
        MOSCOLLECTOR,
        MOSVODOSTOK,
        MSPPN,
        DEPECO,
        DEP_TSZN,
        RZD
    }
    public enum CoreDangerFactor
    {
        OpenFlame,
        ToxicSmoke,
        GasLeak,
        PhysicalViolence,
        KineticImpact,
        SomaticAttack
    }
    public enum EnvironmentalModifier
    {
        LockedSpace,
        AggressiveCrowd,
        SecondaryRisk,
        StructuralDeformation,
        SensoryDeprivation,
        NoComplications
    }
    public enum HumanBioState
    {
        AcuteBloodLoss,
        Asphyxia,
        VitalFailure,
        TraumaticShock,
        PsychogenicStupor,
        NoInjuries
    }
    public enum CardState
    {
        Draft,
        SentToServices,
        ConfirmedByDDS
    }
    public enum DdsProfile
    {
        Universal_112,
        Mosvodokanal,
        Moscollector,
        GasService,
        HousingServices,
        Gormost,
        ElectricService
    }
    [Flags]
    public enum ClassifierTag
    {
        None = 0,
        ResidentialBuilding = 1,
        School = 2,
        Hospital = 4,
        Underground = 8,
        Road = 16,
        Bridge = 32,
        Park = 64,
        IndustrialZone = 128,
        Fire = 256,
        Flood = 512,
        GasLeak = 1024,
        Collapse = 2048,
        Violence = 4096,
        Electrocution = 8192,
        TrafficAccident = 16384,
        ExplosionRisk = 32768,
        PeopleTrapped = 65536,
        Casualties = 131072,
        ChildrenAtRisk = 262144,
        InfrastructureDamage = 524288,
        EvacuationNeeded = 1048576,
        Smoke = 2097152,
        PublicBuilding = 4194304,
        NaturalArea = 8388608,
        CriticalCondition = 16777216,
        Bleeding = 33554432,
        Fracture = 67108864,
        MissingPerson = 134217728
    }
    public enum CallerPersona
    {
        ElderlyNeighbor,
        ProfessionalWorker,
        PanickedParent,
        IndifferentPasserby,
        Child,
        DrunkPerson,
        AggressiveResident
    }
    public static class EnumExtensions
    {
        public static string GetDisplayName(this IncidentType type)
        {
            return type switch
            {
                IncidentType.Service101 =>
                    "101",

                IncidentType.Service102 =>
                    "102",

                IncidentType.Service103 =>
                    "103",

                IncidentType.Service104 =>
                    "104",

                IncidentType.CityInfrastructureAccident =>
                    "Авария в городском хозяйстве",

                IncidentType.TransportObjectAccident =>
                    "Происшествие на транспортном объекте",

                IncidentType.HydraulicStructureAccident =>
                    "Авария на гидротехническом сооружении",

                IncidentType.HazardousProductionAccident =>
                    "Авария на опасном или производственном объекте",

                IncidentType.ServiceThanks =>
                    "Благодарность службе",

                IncidentType.UAV =>
                    "Беспилотный летательный аппарат",

                IncidentType.Explosion =>
                    "Взрыв",

                IncidentType.RoadObstruction =>
                    "Дорожное препятствие",

                IncidentType.TrafficAccident =>
                    "Дорожно-транспортное происшествие",

                IncidentType.ComplaintAboutServices =>
                    "Жалоба на работу службы",

                IncidentType.Animals =>
                    "Происшествие с животным",

                IncidentType.Consultation =>
                    "Консультация",

                IncidentType.Collapse =>
                    "Обрушение",

                IncidentType.AssistanceToServices =>
                    "Помощь действующим службам",

                IncidentType.NaturalDisaster =>
                    "Природное происшествие",

                IncidentType.OtherIncident =>
                    "Прочее происшествие",

                IncidentType.Radiation =>
                    "Радиационная опасность",

                IncidentType.BrokenThermometer =>
                    "Разбитый термометр",

                IncidentType.ChildInDanger =>
                    "Ребёнок в опасности",

                IncidentType.WaterAccumulation =>
                    "Скопление воды",

                IncidentType.FatalOutcome =>
                    "Предполагаемый смертельный исход",

                IncidentType.SocialAssistance =>
                    "Социальная помощь",

                IncidentType.Training =>
                    "Учебный вызов",

                IncidentType.ExplosionOrTerroristThreat =>
                    "Угроза взрыва или террористического акта",

                IncidentType.HazardousSubstanceOrRadiationThreat =>
                    "Угроза выброса опасных веществ или радиации",

                IncidentType.CollapseThreat =>
                    "Угроза обрушения",

                IncidentType.PersonInDanger =>
                    "Человек в опасности",

                IncidentType.EnvironmentalIncident =>
                    "Экологическое происшествие",

                _ =>
                    type.ToString()
            };
        }

        public static string GetCode(this IncidentType type)
        {
            return type switch
            {
                IncidentType.Service101 =>
                    "101",

                IncidentType.Service102 =>
                    "102",

                IncidentType.Service103 =>
                    "103",

                IncidentType.Service104 =>
                    "104",

                IncidentType.UAV =>
                    "БПЛА",

                IncidentType.Explosion =>
                    "Взрыв",

                IncidentType.Collapse =>
                    "Обрушение",

                IncidentType.TrafficAccident =>
                    "ДТП",

                IncidentType.FatalOutcome =>
                    "Смертельный исход",

                _ =>
                    type.ToString()
            };
        }

        // Основная характеристика происшествия.
        // Текст написан от второго лица, потому что сама модель является персонажем.
        public static string GetGeneralDescription(this IncidentType type)
        {
            return type switch
            {
                IncidentType.Service101 =>
                    "Ты звонишь в 112, потому что рядом происходит опасная ситуация, для которой может потребоваться пожарно-спасательная помощь.",

                IncidentType.Service102 =>
                    "Ты звонишь в 112 из-за ситуации, в которой может потребоваться вмешательство полиции.",

                IncidentType.Service103 =>
                    "Ты звонишь в 112 из-за человека, которому может потребоваться срочная медицинская помощь.",

                IncidentType.Service104 =>
                    "Ты обнаружил возможную проблему с газом или газовым оборудованием и сообщаешь о ней оператору.",

                IncidentType.CityInfrastructureAccident =>
                    "Ты находишься рядом с аварией или повреждением городской инфраструктуры и сообщаешь об этом.",

                IncidentType.TransportObjectAccident =>
                    "Ты находишься на месте происшествия, связанного с транспортным объектом, и рассказываешь оператору, что произошло.",

                IncidentType.HydraulicStructureAccident =>
                    "Ты находишься рядом с аварией на гидротехническом сооружении и сообщаешь об этом.",

                IncidentType.HazardousProductionAccident =>
                    "Ты находишься на месте аварии на производственном или потенциально опасном объекте.",

                IncidentType.ServiceThanks =>
                    "Ты звонишь в 112, чтобы поблагодарить одну из служб.",

                IncidentType.UAV =>
                    "Ты заметил беспилотный летательный аппарат и сообщаешь оператору, где и что ты увидел.",

                IncidentType.Explosion =>
                    "Ты только что заметил произошедший взрыв или его непосредственные последствия и сообщаешь об этом.",

                IncidentType.RoadObstruction =>
                    "Ты видишь препятствие на дороге, которое мешает движению, и сообщаешь об этом.",

                IncidentType.TrafficAccident =>
                    "Ты находишься рядом с дорожно-транспортным происшествием и сообщаешь оператору, что произошло.",

                IncidentType.ComplaintAboutServices =>
                    "Ты звонишь из-за проблемы с работой какой-либо службы и объясняешь оператору, что тебя беспокоит.",

                IncidentType.Animals =>
                    "Ты столкнулся с происшествием, связанным с животным или животными, и сообщаешь об этом.",

                IncidentType.Consultation =>
                    "Ты звонишь в 112, чтобы получить необходимую консультацию.",

                IncidentType.Collapse =>
                    "Ты находишься рядом с местом обрушения конструкции или объекта и сообщаешь оператору, что произошло.",

                IncidentType.AssistanceToServices =>
                    "Ты находишься на месте происшествия, где действующим службам требуется дополнительная помощь.",

                IncidentType.NaturalDisaster =>
                    "Ты находишься в месте, где происходит опасное природное явление, и сообщаешь об этом.",

                IncidentType.OtherIncident =>
                    "Ты столкнулся с происшествием, которое не относится к отдельной специализированной категории, и сообщаешь о нём.",

                IncidentType.Radiation =>
                    "Ты обнаружил возможную радиационную опасность и сообщаешь об этом оператору.",

                IncidentType.BrokenThermometer =>
                    "Ты разбил или обнаружил разбитый термометр и сообщаешь об этом из-за возможной опасности.",

                IncidentType.ChildInDanger =>
                    "Ты обнаружил ребёнка в потенциально опасной ситуации и звонишь за помощью.",

                IncidentType.WaterAccumulation =>
                    "Ты видишь значительное скопление воды или затопление и сообщаешь оператору.",

                IncidentType.FatalOutcome =>
                    "Ты обнаружил человека, который не реагирует или предположительно погиб, и сообщаешь об этом.",

                IncidentType.SocialAssistance =>
                    "Ты столкнулся с ситуацией, в которой тебе или другому человеку требуется социальная помощь.",

                IncidentType.Training =>
                    "Ты участвуешь в учебном вызове и отыгрываешь обычное обращение в службу 112.",

                IncidentType.ExplosionOrTerroristThreat =>
                    "Ты получил или заметил информацию об угрозе взрыва или террористического акта и сообщаешь об этом.",

                IncidentType.HazardousSubstanceOrRadiationThreat =>
                    "Ты обнаружил признаки возможного выброса опасного вещества или радиационной угрозы и сообщаешь об этом.",

                IncidentType.CollapseThreat =>
                    "Ты находишься рядом с конструкцией, которая может обрушиться, и сообщаешь оператору об опасности.",

                IncidentType.PersonInDanger =>
                    "Ты оказался в опасной ситуации или видишь человека, которому требуется помощь.",

                IncidentType.EnvironmentalIncident =>
                    "Ты обнаружил локальное загрязнение или другую экологическую угрозу и сообщаешь об этом.",

                _ =>
                    "Ты столкнулся с происшествием и сообщаешь о нём оператору службы 112."
            };
        }

        // Более конкретное описание происходящего.
        // Можно передавать в PromptBuilder отдельно от общего типа.
        public static string GetScenarioPrompt(this IncidentType type)
        {
            return type switch
            {
                IncidentType.Service101 =>
                    "Ты находишься в ситуации, где существует опасность для людей или имущества и может потребоваться пожарно-спасательная служба.",

                IncidentType.Service102 =>
                    "Ты находишься в ситуации, связанной с конфликтом, нарушением порядка, угрозой людям или другим происшествием, где может потребоваться полиция.",

                IncidentType.Service103 =>
                    "Ты находишься рядом с человеком, у которого ухудшилось самочувствие, есть травма или другое состояние, требующее медицинской оценки.",

                IncidentType.Service104 =>
                    "Ты обнаружил возможную утечку газа или проблему с газовым оборудованием.",

                IncidentType.CityInfrastructureAccident =>
                    "Ты видишь аварию или повреждение объекта городской инфраструктуры.",

                IncidentType.TransportObjectAccident =>
                    "Ты находишься на месте происшествия, связанного с транспортной инфраструктурой.",

                IncidentType.HydraulicStructureAccident =>
                    "Ты находишься рядом с повреждённым или аварийно работающим гидротехническим сооружением.",

                IncidentType.HazardousProductionAccident =>
                    "Ты находишься на производственном или потенциально опасном объекте, где произошла авария.",

                IncidentType.ServiceThanks =>
                    "Ты хочешь поблагодарить службу за оказанную помощь.",

                IncidentType.UAV =>
                    "Ты заметил беспилотный летательный аппарат и можешь описывать только то, что действительно наблюдал.",

                IncidentType.Explosion =>
                    "Ты находишься рядом с местом, где произошёл взрыв, и можешь описывать его непосредственные последствия.",

                IncidentType.RoadObstruction =>
                    "Ты видишь препятствие, которое мешает безопасному движению по дороге.",

                IncidentType.TrafficAccident =>
                    "Ты видишь столкновение транспортных средств или другую дорожную аварию.",

                IncidentType.ComplaintAboutServices =>
                    "Ты недоволен работой службы и объясняешь оператору конкретную проблему.",

                IncidentType.Animals =>
                    "Ты столкнулся с проблемой, связанной с животным или животными.",

                IncidentType.Consultation =>
                    "Ты задаёшь вопрос оператору и ожидаешь получить необходимую информацию.",

                IncidentType.Collapse =>
                    "Ты находишься рядом с уже произошедшим обрушением конструкции или объекта.",

                IncidentType.AssistanceToServices =>
                    "Ты находишься на месте, где действующим службам требуется дополнительная помощь.",

                IncidentType.NaturalDisaster =>
                    "Ты находишься в зоне природного явления, которое создаёт опасность для людей или имущества.",

                IncidentType.OtherIncident =>
                    "Ты находишься в ситуации, которая не относится к другим специализированным категориям.",

                IncidentType.Radiation =>
                    "Ты обнаружил возможный источник радиационной опасности или признаки радиационного воздействия.",

                IncidentType.BrokenThermometer =>
                    "Ты обнаружил разбитый термометр и беспокоишься из-за возможного опасного вещества.",

                IncidentType.ChildInDanger =>
                    "Ты видишь ребёнка в ситуации, представляющей опасность для его безопасности.",

                IncidentType.WaterAccumulation =>
                    "Ты видишь большое скопление воды или затопление, которое мешает нормальному использованию помещения, дороги или территории.",

                IncidentType.FatalOutcome =>
                    "Ты обнаружил человека без нормальной реакции и сообщаешь оператору о его состоянии.",

                IncidentType.SocialAssistance =>
                    "Ты столкнулся с ситуацией, в которой человеку необходима социальная или бытовая помощь.",

                IncidentType.Training =>
                    "Ты участвуешь в учебном обращении в службу 112.",

                IncidentType.ExplosionOrTerroristThreat =>
                    "Ты получил информацию о возможной угрозе взрыва или террористического акта и сообщаешь её оператору.",

                IncidentType.HazardousSubstanceOrRadiationThreat =>
                    "Ты обнаружил признаки возможного выброса опасного вещества или радиационной угрозы.",

                IncidentType.CollapseThreat =>
                    "Ты находишься рядом с конструкцией, которая может обрушиться, но её полное обрушение ещё не произошло.",

                IncidentType.PersonInDanger =>
                    "Ты или находящийся рядом с тобой человек оказался в опасной ситуации и нуждается в помощи.",

                IncidentType.EnvironmentalIncident =>
                    "Ты обнаружил загрязнение или другую локальную экологическую угрозу.",

                _ =>
                    "Ты находишься в месте происшествия и сообщаешь оператору то, что тебе известно."
            };
        }

        public static string GetSymptomsDescription(this IncidentType type)
        {
            return type switch
            {
                IncidentType.Service103 =>
                    "Ты видишь или испытываешь резкое ухудшение самочувствия; конкретные симптомы нужно уточнить.",

                IncidentType.TrafficAccident =>
                    "После ДТП возможны травмы, боль, ушибы или шок.",

                IncidentType.Explosion =>
                    "После взрыва возможны травмы, ожоги, ушибы или дезориентация.",

                IncidentType.Collapse =>
                    "После обрушения у находящихся рядом людей возможны травмы.",

                IncidentType.FatalOutcome =>
                    "Человек не реагирует или не подаёт обычных признаков сознания.",

                IncidentType.ChildInDanger =>
                    "Состояние ребёнка пока неизвестно и требует уточнения.",

                IncidentType.PersonInDanger =>
                    "Состояние человека требует уточнения.",

                IncidentType.ExplosionOrTerroristThreat =>
                    "Информация о пострадавших отсутствует или требует уточнения.",

                IncidentType.CollapseThreat =>
                    "Состояние людей в опасной зоне требует уточнения.",

                _ =>
                    "Информация о пострадавших или их состоянии требует уточнения."
            };
        }

        public static string GetActorPrompt(this CoreDangerFactor factor)
        {
            return factor switch
            {
                CoreDangerFactor.OpenFlame =>
                    "Ты находишься рядом с открытым огнём или пожаром. Ты можешь видеть пламя, чувствовать жар и замечать дым.",

                CoreDangerFactor.ToxicSmoke =>
                    "Ты находишься в сильно задымлённом месте. Тебе может быть трудно видеть происходящее, ты можешь кашлять или испытывать затруднение дыхания.",

                CoreDangerFactor.GasLeak =>
                    "Ты обнаружил возможную утечку газа. Ты можешь чувствовать характерный запах или слышать свист и опасаться возгорания.",

                CoreDangerFactor.PhysicalViolence =>
                    "Ты находишься рядом с конфликтом или физической угрозой. Ты видишь происходящее и понимаешь, что может потребоваться полиция.",

                CoreDangerFactor.KineticImpact =>
                    "Ты оказался рядом с сильным столкновением, ударом или разрушением. Ты можешь быть дезориентирован и описывать только то, что видишь вокруг.",

                CoreDangerFactor.SomaticAttack =>
                    "Ты видишь, что у человека резко ухудшилось физическое состояние, и можешь описывать только заметные тебе симптомы.",

                _ =>
                    "Ты находишься в текущей ситуации и описываешь только происходящее в ней."
            };
        }

        public static string GetActorPrompt(this EnvironmentalModifier modifier)
        {
            return modifier switch
            {
                EnvironmentalModifier.LockedSpace =>
                    "Ты находишься в замкнутом или заблокированном помещении и не можешь самостоятельно нормально выйти.",

                EnvironmentalModifier.AggressiveCrowd =>
                    "Вокруг тебя находится беспокойная или агрессивная толпа. Люди шумят и мешают тебе спокойно разговаривать.",

                EnvironmentalModifier.SecondaryRisk =>
                    "Помимо основной опасности рядом с тобой существует дополнительная угроза, которая может ухудшить ситуацию.",

                EnvironmentalModifier.StructuralDeformation =>
                    "Окружающие конструкции повреждены, поэтому тебе трудно или опасно покинуть место происшествия.",

                EnvironmentalModifier.SensoryDeprivation =>
                    "Тебе трудно ориентироваться из-за темноты, дыма, плохой видимости, шума или других ограничений.",

                EnvironmentalModifier.NoComplications =>
                    "Дополнительных осложняющих факторов рядом с тобой нет.",

                _ =>
                    "Дополнительные обстоятельства текущей ситуации тебе неизвестны."
            };
        }

        public static string GetActorPrompt(this HumanBioState state)
        {
            return state switch
            {
                HumanBioState.AcuteBloodLoss =>
                    "Ты видишь у пострадавшего признаки значительной кровопотери.",

                HumanBioState.Asphyxia =>
                    "Ты видишь, что пострадавшему тяжело дышать.",

                HumanBioState.VitalFailure =>
                    "Ты видишь, что пострадавший не реагирует или его состояние резко ухудшилось.",

                HumanBioState.TraumaticShock =>
                    "Ты видишь у пострадавшего тяжёлое состояние после травмы, сильную боль или выраженный шок.",

                HumanBioState.PsychogenicStupor =>
                    "Ты видишь, что человек находится в состоянии сильного психологического потрясения и почти не реагирует на происходящее.",

                HumanBioState.NoInjuries =>
                    "Ты не видишь явных травм или выраженных физических повреждений.",

                _ =>
                    "Подробные сведения о состоянии пострадавшего тебе неизвестны."
            };
        }

        public static string GetActorPrompt(this DdsProfile profile)
        {
            return profile switch
            {
                DdsProfile.Mosvodokanal =>
                    "Ты столкнулся с проблемой, связанной с водой, водоснабжением или канализацией. Используй технические термины только если твоя роль это позволяет.",

                DdsProfile.Moscollector =>
                    "Ты находишься в подземном коллекторе или тоннеле. Там может быть темно, сыро и трудно попасть внутрь или выбраться.",

                DdsProfile.GasService =>
                    "Ты столкнулся с возможной утечкой газа или проблемой газового оборудования.",

                DdsProfile.HousingServices =>
                    "Ты столкнулся с проблемой в жилом объекте: в подъезде, лифте, на крыше, фасаде или в другой части дома.",

                DdsProfile.Gormost =>
                    "Ты находишься на мосту, эстакаде или путепроводе, где произошло происшествие.",

                DdsProfile.ElectricService =>
                    "Ты столкнулся с проблемой электрических проводов, электроснабжения или электрооборудования.",

                DdsProfile.Universal_112 =>
                    "Ты находишься в обычной чрезвычайной ситуации, обстоятельства которой необходимо объяснить оператору.",

                _ =>
                    "Ты находишься в обычной ситуации, требующей обращения в службу 112."
            };
        }

        public static string GetActorPrompt(this CallerPersona persona)
        {
            return persona switch
            {
                CallerPersona.ElderlyNeighbor =>
                    "Ты пожилой сосед. Говоришь простыми словами, можешь забывать отдельные детали и не знать технических терминов.",

                CallerPersona.ProfessionalWorker =>
                    "Ты профессиональный работник. Хорошо понимаешь происходящее и можешь использовать технические термины, если они тебе действительно известны.",

                CallerPersona.PanickedParent =>
                    "Ты встревоженный родитель. В первую очередь думаешь о безопасности ребёнка. Можешь говорить эмоционально и повторять важные детали.",

                CallerPersona.IndifferentPasserby =>
                    "Ты случайный прохожий. Говоришь только о том, что действительно видел или слышал сам, и не знаешь чужих подробностей.",

                CallerPersona.Child =>
                    "Ты ребёнок. Говоришь коротко и простыми словами. Можешь не знать точный адрес и плохо понимать сложные вопросы.",

                CallerPersona.DrunkPerson =>
                    "Ты нетрезвый человек. Можешь говорить сбивчиво, повторяться и иногда путать несущественные детали, но не меняешь само происшествие.",

                CallerPersona.AggressiveResident =>
                    "Ты раздражённый жилец. Говоришь резко, жалуешься на проблему и требуешь помощи.",

                _ =>
                    "Ты обычный человек, оказавшийся рядом с происшествием."
            };
        }

        public static IEnumerable<string> GetActorPrompts(this ClassifierTag tags)
        {
            // МЕСТО

            if (tags.HasFlag(ClassifierTag.ResidentialBuilding))
                yield return "Ты находишься в жилом многоквартирном доме или рядом с ним.";

            if (tags.HasFlag(ClassifierTag.School))
                yield return "Ты находишься на территории школы или другого детского учреждения.";

            if (tags.HasFlag(ClassifierTag.Hospital))
                yield return "Ты находишься в больнице или другом медицинском учреждении.";

            if (tags.HasFlag(ClassifierTag.Underground))
                yield return "Ты находишься под землёй, в тоннеле, подвале или коллекторе.";

            if (tags.HasFlag(ClassifierTag.Road))
                yield return "Ты находишься на проезжей части или рядом с дорогой.";

            if (tags.HasFlag(ClassifierTag.Bridge))
                yield return "Ты находишься на мосту, эстакаде или путепроводе.";

            if (tags.HasFlag(ClassifierTag.Park))
                yield return "Ты находишься в парке или другой зоне отдыха.";

            if (tags.HasFlag(ClassifierTag.IndustrialZone))
                yield return "Ты находишься на промышленной территории, складе или производственном объекте.";

            if (tags.HasFlag(ClassifierTag.PublicBuilding))
                yield return "Ты находишься в общественном здании.";

            if (tags.HasFlag(ClassifierTag.NaturalArea))
                yield return "Ты находишься на природной территории или за пределами плотной городской застройки.";


            // ОПАСНОСТЬ

            if (tags.HasFlag(ClassifierTag.Fire))
                yield return "Ты видишь пожар или открытое пламя.";

            if (tags.HasFlag(ClassifierTag.Smoke))
                yield return "Вокруг тебя сильное задымление, из-за которого плохо видно происходящее.";

            if (tags.HasFlag(ClassifierTag.Flood))
                yield return "Ты видишь затопление или большое количество воды.";

            if (tags.HasFlag(ClassifierTag.GasLeak))
                yield return "Ты замечаешь признаки возможной утечки газа.";

            if (tags.HasFlag(ClassifierTag.Collapse))
                yield return "Ты видишь, что конструкция обрушилась.";

            if (tags.HasFlag(ClassifierTag.Violence))
                yield return "Ты видишь физическую угрозу или насилие.";

            if (tags.HasFlag(ClassifierTag.Electrocution))
                yield return "Ты видишь повреждённые электрические элементы, которые могут быть опасны.";

            if (tags.HasFlag(ClassifierTag.TrafficAccident))
                yield return "Ты видишь дорожно-транспортное происшествие.";

            if (tags.HasFlag(ClassifierTag.ExplosionRisk))
                yield return "Ты понимаешь, что на месте существует риск взрыва.";


            // ЛЮДИ

            if (tags.HasFlag(ClassifierTag.PeopleTrapped))
                yield return "Ты знаешь, что люди не могут самостоятельно выбраться из опасной зоны.";

            if (tags.HasFlag(ClassifierTag.Casualties))
                yield return "Ты знаешь, что на месте есть пострадавшие.";

            if (tags.HasFlag(ClassifierTag.ChildrenAtRisk))
                yield return "Ты видишь или знаешь, что в опасной зоне находятся дети.";

            if (tags.HasFlag(ClassifierTag.Bleeding))
                yield return "Ты видишь у пострадавшего кровотечение.";

            if (tags.HasFlag(ClassifierTag.Fracture))
                yield return "Ты видишь признаки возможной травмы конечности или другого перелома.";

            if (tags.HasFlag(ClassifierTag.CriticalCondition))
                yield return "Ты понимаешь, что состояние человека или ситуация в целом критические.";

            if (tags.HasFlag(ClassifierTag.MissingPerson))
                yield return "Ты сообщаешь о пропавшем человеке и можешь описывать только известные тебе обстоятельства.";


            // ПОСЛЕДСТВИЯ

            if (tags.HasFlag(ClassifierTag.InfrastructureDamage))
                yield return "Ты видишь повреждение городской или объектовой инфраструктуры.";

            if (tags.HasFlag(ClassifierTag.EvacuationNeeded))
                yield return "Ты понимаешь, что людям необходимо покинуть опасную зону.";
        }
    }

    public static class TagMetadata
    {
        public static readonly HashSet<ClassifierTag> CriticalTags = new()
    {
        ClassifierTag.Fire,
        ClassifierTag.GasLeak,
        ClassifierTag.ChildrenAtRisk,
        ClassifierTag.Casualties,
        ClassifierTag.PeopleTrapped,
        ClassifierTag.ExplosionRisk
    };

        public static bool IsCritical(ClassifierTag tag)
        {
            return CriticalTags.Contains(tag);
        }
    }
}