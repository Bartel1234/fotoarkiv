package main
import("encoding/json";"errors";"os";"path/filepath";"testing")
func TestLocalDownloadTelemetry(t *testing.T){
 dir:=t.TempDir();t.Setenv("PHOTOHARBOR_RUN_STATE",dir);t.Setenv("PHOTOHARBOR_ATTEMPT","1")
 recordDownload("https://photos.google.com/photo/AF1Qtest","movie.mp4",100)
 data,_:=os.ReadFile(filepath.Join(dir,"downloads.jsonl"));var entry map[string]interface{};if err:=json.Unmarshal(data,&entry);err!=nil{t.Fatal(err)}
 if entry["kind"]!="video"||entry["bytes"]!=float64(100){t.Fatal(entry)}
 data,_=os.ReadFile(filepath.Join(dir,"live.json"));json.Unmarshal(data,&entry);if entry["completed_bytes"]!=float64(100){t.Fatal(entry)}
 recordFailure("https://photos.google.com/photo/AF1Qtest",errors.New("download stalled"),"download")
 data,_=os.ReadFile(filepath.Join(dir,"download-failure.json"));json.Unmarshal(data,&entry);if entry["retryable"]!=true{t.Fatal(entry)}
 recordFailure("https://photos.google.com/photo/AF1Qtest",errors.New("timeout"),"organization")
 data,_=os.ReadFile(filepath.Join(dir,"download-failure.json"));json.Unmarshal(data,&entry);if entry["retryable"]!=false{t.Fatal(entry)}
}
