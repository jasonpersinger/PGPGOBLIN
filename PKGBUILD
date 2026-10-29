# Maintainer: Jason Persinger <jason.persinger@gmail.com>
pkgname=pgpgoblin
pkgver=1.1.0
pkgrel=1
pkgdesc="Minimalist 8-bit inspired PGP notepad/scratchpad interfacing directly with native system GnuPG"
arch=('any')
url="https://github.com/jasonpersinger/PGPGOBLIN"
license=('MIT')
depends=('gnupg' 'pinentry' 'python' 'python-gnupg' 'python-pyqt6')
optdepends=('python-pyqt5: Qt5 backend fallback')
source=("${pkgname}-${pkgver}.tar.gz::https://github.com/jasonpersinger/PGPGOBLIN/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('1a5ff7d97196b16870210e72daaae1c8a69792cdd95b5178349f3af6408d25b8')

package() {
    cd "${srcdir}/PGPGOBLIN-${pkgver}"
    install -Dm755 "pgpgoblin.py" "${pkgdir}/usr/bin/pgpgoblin"
    install -Dm644 "pgpgoblin.desktop" "${pkgdir}/usr/share/applications/pgpgoblin.desktop"
    install -Dm644 "pgpgoblin.svg" "${pkgdir}/usr/share/icons/hicolor/scalable/apps/pgpgoblin.svg"
    install -Dm644 "pgpgoblin_icon.png" "${pkgdir}/usr/share/icons/hicolor/512x512/apps/pgpgoblin.png"
    install -Dm644 "LICENSE" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
