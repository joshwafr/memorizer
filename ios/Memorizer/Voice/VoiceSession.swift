import AVFoundation
import Speech
import SwiftUI

@MainActor
final class VoiceSession: NSObject, ObservableObject {
    enum State: Equatable {
        case idle
        case starting
        case speakingQuestion
        case listening
        case grading
        case speakingFeedback
        case finished
        case error(String)
    }

    @Published var state: State = .idle
    @Published var queue: [DueCard] = []
    @Published var index = 0
    @Published var liveTranscript = ""
    @Published var lastResult: AnswerResult?

    private let synthesizer = AVSpeechSynthesizer()
    private var audioPlayer: AVAudioPlayer?
    private var speechContinuation: CheckedContinuation<Void, Never>?

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var silenceTimer: Timer?
    private var finishedListening = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    // MARK: - Session control

    func start() async {
        state = .starting
        let micOK = await requestPermissions()
        guard micOK else {
            state = .error("Microphone or speech permission denied. Enable both in Settings.")
            return
        }
        do {
            try configureAudioSession()
            queue = try await API.dueCards()
        } catch {
            state = .error(error.localizedDescription)
            return
        }
        index = 0
        guard !queue.isEmpty else {
            await speak("No cards are due right now. Nice work.")
            state = .finished
            return
        }
        await speak("Starting your review. \(queue.count) cards due.")
        await askCurrent()
    }

    func stop() {
        stopListening(submit: false)
        synthesizer.stopSpeaking(at: .immediate)
        audioPlayer?.stop()
        state = .idle
        liveTranscript = ""
        lastResult = nil
    }

    /// Tap-to-finish: user signals they're done answering.
    func finishAnswer() {
        stopListening(submit: true)
    }

    func skipCard() {
        stopListening(submit: false)
        Task { await advance() }
    }

    private func askCurrent() async {
        guard index < queue.count else {
            await speak("Session complete. See you next time.")
            state = .finished
            return
        }
        state = .speakingQuestion
        lastResult = nil
        let card = queue[index]
        var intro = ""
        if let title = card.sourceTitle, !title.isEmpty {
            intro = "From \(title). "
        }
        await speak(intro + card.question)
        beginListening()
    }

    private func advance() async {
        index += 1
        liveTranscript = ""
        await askCurrent()
    }

    // MARK: - Listening (on-device speech recognition)

    private func beginListening() {
        liveTranscript = ""
        finishedListening = false
        state = .listening

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if recognizer?.supportsOnDeviceRecognition == true {
            request.requiresOnDeviceRecognition = true
        }
        recognitionRequest = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            state = .error("Couldn't access the microphone: \(error.localizedDescription)")
            return
        }

        recognitionTask = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor [weak self] in
                guard let self, self.state == .listening else { return }
                if let result {
                    self.liveTranscript = result.bestTranscription.formattedString
                    self.restartSilenceTimer()
                }
                if error != nil && self.liveTranscript.isEmpty {
                    // Recognition failed before any speech — keep waiting rather than crash the session.
                    self.restartSilenceTimer(seconds: 6)
                }
            }
        }
        restartSilenceTimer(seconds: 10)  // generous window to start talking
    }

    private func restartSilenceTimer(seconds: TimeInterval = 2.2) {
        silenceTimer?.invalidate()
        silenceTimer = Timer.scheduledTimer(withTimeInterval: seconds, repeats: false) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.stopListening(submit: true)
            }
        }
    }

    private func stopListening(submit: Bool) {
        guard state == .listening, !finishedListening else { return }
        finishedListening = true
        silenceTimer?.invalidate()
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionRequest = nil
        recognitionTask = nil

        guard submit else { return }
        let answer = liveTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        Task { await submitAnswer(answer) }
    }

    private func submitAnswer(_ answer: String) async {
        guard index < queue.count else { return }
        if answer.isEmpty {
            await speak("I didn't catch anything. Let's come back to that one.")
            await advance()
            return
        }
        state = .grading
        do {
            let result = try await API.answer(cardId: queue[index].id, text: answer)
            lastResult = result
            state = .speakingFeedback
            await speak("\(spokenGrade(result.grade)). \(result.feedback)")
            await advance()
        } catch {
            await speak("Grading failed. Skipping this card.")
            await advance()
        }
    }

    private func spokenGrade(_ grade: String) -> String {
        switch grade {
        case "easy": return "Easy — you nailed it"
        case "good": return "Good"
        case "hard": return "Partially right"
        default: return "Not quite"
        }
    }

    // MARK: - Speaking (OpenAI TTS via backend, AVSpeech fallback)

    private func speak(_ text: String) async {
        if let audio = try? await fetchTTS(text), await play(audio) {
            return
        }
        await speakWithSystemVoice(text)
    }

    private func fetchTTS(_ text: String) async throws -> Data {
        var req = URLRequest(url: API.baseURL.appendingPathComponent("tts"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["text": text])
        let (data, response) = try await URLSession.shared.data(for: req)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw APIError.http((response as? HTTPURLResponse)?.statusCode ?? 0, "tts")
        }
        return data
    }

    private func play(_ data: Data) async -> Bool {
        await withCheckedContinuation { continuation in
            do {
                audioPlayer = try AVAudioPlayer(data: data)
                playbackContinuation = continuation
                audioPlayer?.delegate = self
                audioPlayer?.play()
            } catch {
                continuation.resume(returning: false)
            }
        }
    }

    private var playbackContinuation: CheckedContinuation<Bool, Never>?

    private func speakWithSystemVoice(_ text: String) async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            speechContinuation = continuation
            let utterance = AVSpeechUtterance(string: text)
            utterance.rate = 0.5
            synthesizer.speak(utterance)
        }
    }

    // MARK: - Plumbing

    private func configureAudioSession() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .spokenAudio,
                                options: [.defaultToSpeaker, .allowBluetooth, .allowBluetoothA2DP])
        try session.setActive(true)
    }

    private func requestPermissions() async -> Bool {
        let mic = await withCheckedContinuation { cont in
            AVAudioApplication.requestRecordPermission { cont.resume(returning: $0) }
        }
        let speech = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0 == .authorized) }
        }
        return mic && speech
    }
}

extension VoiceSession: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                                       didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.speechContinuation?.resume()
            self.speechContinuation = nil
        }
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                                       didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.speechContinuation?.resume()
            self.speechContinuation = nil
        }
    }
}

extension VoiceSession: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            self.playbackContinuation?.resume(returning: flag)
            self.playbackContinuation = nil
        }
    }
}
