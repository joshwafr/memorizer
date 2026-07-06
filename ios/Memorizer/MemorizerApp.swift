import SwiftUI

@main
struct MemorizerApp: App {
    var body: some Scene {
        WindowGroup {
            TabView {
                HomeView()
                    .tabItem { Label("Home", systemImage: "tray.and.arrow.down") }
                ReviewView()
                    .tabItem { Label("Review", systemImage: "brain.head.profile") }
                VoiceView()
                    .tabItem { Label("Voice", systemImage: "waveform") }
                CardsView()
                    .tabItem { Label("Cards", systemImage: "rectangle.stack") }
            }
        }
    }
}
