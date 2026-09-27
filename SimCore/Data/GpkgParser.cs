using Microsoft.Data.Sqlite;
using SimCore.Entities; // ← Используем модели отсюда
using System.Text.Json;
using System.IO;

namespace SimCore.Data
{
    public class GpkgParser
    {
        public List<StreetWithHouses> ParseAddresses(string gpkgPath)
        {
            Console.WriteLine($"📖 Чтение GPKG файла: {gpkgPath}");
            var streetDict = new Dictionary<string, StreetWithHouses>();

            using var connection = new SqliteConnection($"Data Source={gpkgPath}");
            connection.Open();

            Console.WriteLine("\n🔍 Парсинг точек (points)...");
            ParseTable(connection, "points", streetDict);

            Console.WriteLine("\n🔍 Парсинг полигонов зданий (multipolygons)...");
            ParseTable(connection, "multipolygons", streetDict);

            Console.WriteLine($"\n✅ Итого найдено домов: {streetDict.Values.Sum(s => s.Houses.Count)}");
            Console.WriteLine($"✅ Улиц с домами: {streetDict.Count}");

            return streetDict.Values.ToList();
        }

        private void ParseTable(SqliteConnection connection, string tableName, Dictionary<string, StreetWithHouses> streetDict)
        {
            var command = connection.CreateCommand();
            command.CommandText = $@"
                SELECT other_tags, geom 
                FROM {tableName} 
                WHERE other_tags LIKE '%addr:housenumber%' 
                  AND other_tags LIKE '%addr:street%'";

            using var reader = command.ExecuteReader();
            int count = 0;
            int errors = 0;

            while (reader.Read())
            {
                try
                {
                    string otherTags = reader.GetString(0);

                    string streetName = ExtractTagValue(otherTags, "addr:street");
                    string houseNumber = ExtractTagValue(otherTags, "addr:housenumber");

                    if (string.IsNullOrEmpty(streetName) || string.IsNullOrEmpty(houseNumber))
                        continue;

                    string buildingType = ExtractTagValue(otherTags, "building") ??
                                         ExtractTagValue(otherTags, "amenity") ??
                                         ExtractTagValue(otherTags, "shop") ??
                                         ExtractTagValue(otherTags, "office");

                    using var stream = reader.GetStream(1);
                    byte[] geomData = new byte[stream.Length];
                    stream.Read(geomData, 0, geomData.Length);

                    var (lat, lon) = ParseGpkgGeometry(geomData);

                    if (lat == 0 || lon == 0)
                        continue;

                    if (!streetDict.ContainsKey(streetName))
                    {
                        streetDict[streetName] = new StreetWithHouses(streetName, "residential", new List<HouseReference>());
                    }

                    streetDict[streetName].Houses.Add(new HouseReference(houseNumber, lat, lon, buildingType));
                    count++;
                }
                catch
                {
                    errors++;
                }
            }

            Console.WriteLine($"   Найдено: {count} | Ошибок: {errors}");
        }

        private string ExtractTagValue(string otherTags, string tagName)
        {
            string search = $"\"{tagName}\"=>\"";
            int startIndex = otherTags.IndexOf(search, StringComparison.OrdinalIgnoreCase);
            if (startIndex == -1) return null;

            startIndex += search.Length;
            int endIndex = otherTags.IndexOf("\"", startIndex);
            if (endIndex == -1) return null;

            return otherTags.Substring(startIndex, endIndex - startIndex);
        }

        private (double Lat, double Lon) ParseGpkgGeometry(byte[] geomData)
        {
            if (geomData.Length < 8) return (0, 0);
            if (geomData[0] != 0x47 || geomData[1] != 0x50) return (0, 0);

            byte flags = geomData[3];
            int envelopeType = (flags >> 1) & 0x07;
            int offset = 8;

            offset += envelopeType switch
            {
                0 => 0,
                1 => 32,
                2 => 40,
                3 => 48,
                4 => 40,
                _ => 0
            };

            if (envelopeType >= 1 && geomData.Length >= 40)
            {
                int envOffset = 8;
                double minX = BitConverter.ToDouble(geomData, envOffset);
                double maxX = BitConverter.ToDouble(geomData, envOffset + 8);
                double minY = BitConverter.ToDouble(geomData, envOffset + 16);
                double maxY = BitConverter.ToDouble(geomData, envOffset + 24);

                double lon = (minX + maxX) / 2;
                double lat = (minY + maxY) / 2;

                if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)
                {
                    return (lat, lon);
                }
            }
            else
            {
                if (geomData.Length < offset + 21) return (0, 0);
                bool isLittleEndian = (geomData[offset] == 1);
                offset++;
                offset += 4;

                double x = ReadDouble(geomData, ref offset, isLittleEndian);
                double y = ReadDouble(geomData, ref offset, isLittleEndian);

                if (y >= -90 && y <= 90 && x >= -180 && x <= 180)
                {
                    return (y, x);
                }
            }

            return (0, 0);
        }

        private double ReadDouble(byte[] data, ref int offset, bool isLittleEndian)
        {
            if (isLittleEndian)
            {
                double val = BitConverter.ToDouble(data, offset);
                offset += 8;
                return val;
            }
            else
            {
                byte[] reversed = new byte[8];
                Array.Copy(data, offset, reversed, 0, 8);
                Array.Reverse(reversed);
                double val = BitConverter.ToDouble(reversed, 0);
                offset += 8;
                return val;
            }
        }

        public void ExportAddressesToJson(List<StreetWithHouses> streets, string outputPath)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? "wwwroot");

            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            };
            string json = JsonSerializer.Serialize(streets, options);
            File.WriteAllText(outputPath, json);
            Console.WriteLine($"💾 Справочник адресов сохранен: {outputPath}");
            Console.WriteLine($"   Всего улиц: {streets.Count}");
            Console.WriteLine($"   Всего домов: {streets.Sum(s => s.Houses.Count)}");
        }
    }
}