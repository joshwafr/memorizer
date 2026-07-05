import UIKit
import UniformTypeIdentifiers

final class ShareViewController: UIViewController {
    private let backendURL = URL(string: "https://app-production-1e43.up.railway.app/capture")!
    private let label = UILabel()
    private let spinner = UIActivityIndicatorView(style: .medium)

    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()
        extractURL { [weak self] url in
            DispatchQueue.main.async {
                guard let self else { return }
                if let url {
                    self.capture(url)
                } else {
                    self.finish(message: "Couldn't find a link in the share.")
                }
            }
        }
    }

    private func setupUI() {
        view.backgroundColor = .clear
        let container = UIView()
        container.backgroundColor = .systemBackground
        container.layer.cornerRadius = 14
        container.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(container)

        label.text = "Capturing…"
        label.font = .preferredFont(forTextStyle: .headline)
        label.numberOfLines = 0
        label.textAlignment = .center
        label.translatesAutoresizingMaskIntoConstraints = false
        spinner.startAnimating()
        spinner.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(label)
        container.addSubview(spinner)

        NSLayoutConstraint.activate([
            container.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            container.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            container.widthAnchor.constraint(equalToConstant: 280),
            spinner.topAnchor.constraint(equalTo: container.topAnchor, constant: 24),
            spinner.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            label.topAnchor.constraint(equalTo: spinner.bottomAnchor, constant: 12),
            label.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
            label.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
            label.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -24),
        ])
    }

    private func extractURL(completion: @escaping (String?) -> Void) {
        let attachments = (extensionContext?.inputItems as? [NSExtensionItem])?
            .compactMap(\.attachments).flatMap { $0 } ?? []

        // Prefer a real URL attachment; fall back to a URL inside shared text.
        if let provider = attachments.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.url.identifier) }) {
            provider.loadItem(forTypeIdentifier: UTType.url.identifier) { item, _ in
                completion((item as? URL)?.absoluteString)
            }
            return
        }
        if let provider = attachments.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) }) {
            provider.loadItem(forTypeIdentifier: UTType.plainText.identifier) { item, _ in
                let text = item as? String ?? ""
                let match = text.split(separator: " ").first { $0.hasPrefix("http") }
                completion(match.map(String.init))
            }
            return
        }
        completion(nil)
    }

    private func capture(_ url: String) {
        var request = URLRequest(url: backendURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["url": url])

        URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            DispatchQueue.main.async {
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                if error == nil && (200..<300).contains(code) {
                    self?.finish(message: "✅ Captured — processing in the background.")
                } else {
                    self?.finish(message: "❌ Capture failed — try again later.")
                }
            }
        }.resume()
    }

    private func finish(message: String) {
        spinner.stopAnimating()
        spinner.isHidden = true
        label.text = message
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
    }
}
