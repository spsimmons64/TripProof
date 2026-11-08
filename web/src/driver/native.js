// What the driver app does differently when it is the TripProofDriver store app rather than a page
// at /drive.
//
//   THE SERVER IS SOMEWHERE ELSE. The store app's pages are on the phone, so "/api" means nothing;
//   every call names the server. Calls go through Capacitor's native HTTP (capacitor.config.json),
//   which is not throttled when the app is in the background the way the web view's own is.
//
//   POSITIONS KEEP COMING WITH THE SCREEN OFF. A browser stops reporting when the phone sleeps; the
//   app runs a location service with a notification saying so, for as long as the driver is
//   signed in.
//
//   THE DRIVER IS TOLD ABOUT TRIPS ON THE PHONE. The app registers with Firebase and gives the
//   server its token; from then on the office's changes arrive as notifications, not texts.
import { Capacitor, registerPlugin } from '@capacitor/core'

export const native = Capacitor.isNativePlatform()
export const API = native ? (import.meta.env.VITE_API_BASE || 'https://dev.tripproofonline.com') : ''
// Set by the build when the app was built with its Firebase configuration. Without it, asking
// Firebase for a token stops the app, so it is not asked.
const PUSH = import.meta.env.VITE_PUSH === '1'

const Background = native ? registerPlugin('BackgroundGeolocation') : null

// Watch the phone's position with the service that survives the screen going off. `onFix` gets
// what navigator.geolocation would have given; `onFail` gets 'denied' or 'nofix'. Returns the stop.
export function watchInBackground(onFix, onFail) {
  let id = null, stopped = false
  Background.addWatcher({
    backgroundTitle: 'TripProof is sharing your location',
    backgroundMessage: 'The office can see where you are until you sign out.',
    requestPermissions: true,
    stale: false,
    distanceFilter: 25,
  }, (loc, err) => {
    if (err) { onFail(err.code === 'NOT_AUTHORIZED' ? 'denied' : 'nofix'); return }
    if (!loc) return
    onFix({ timestamp: loc.time || Date.now(), coords: { latitude: loc.latitude, longitude: loc.longitude } })
  }).then((got) => {
    id = got
    if (stopped) Background.removeWatcher({ id })
  })
  return () => {
    stopped = true
    if (id) Background.removeWatcher({ id })
  }
}

export function openLocationSettings() {
  if (Background) Background.openSettings()
}

// Keep the screen on, the app's way: the browser's wake lock is not there in every web view.
export async function keepAwake(on) {
  try {
    const { KeepAwake } = await import('@capacitor-community/keep-awake')
    await (on ? KeepAwake.keepAwake() : KeepAwake.allowSleep())
  } catch { /* the screen sleeps as normal */ }
}

// Ask to be told about trips, and tell the server where. `send` posts to /device. `heard` is
// called when a notification arrives with the app open, `opened` when the driver taps one, with
// the leg it is about. Returns the stop.
export async function listenForTrips(send, heard, opened) {
  if (!native || !PUSH) return () => {}
  const { FirebaseMessaging } = await import('@capacitor-firebase/messaging')
  const platform = Capacitor.getPlatform()
  const held = []
  try {
    if (platform === 'android') {
      // The channel the server's messages name. High importance: it may sound and show on screen.
      await FirebaseMessaging.createChannel({ id: 'trips', name: 'Trips', description: 'Trips given, changed or taken away',
        importance: 4, visibility: 1, vibration: true })
    }
    const { receive } = await FirebaseMessaging.requestPermissions()
    if (receive !== 'granted') return () => {}
    const { token } = await FirebaseMessaging.getToken()
    if (token) await send({ platform, token })
    held.push(await FirebaseMessaging.addListener('tokenReceived', (e) => e.token && send({ platform, token: e.token })))
    held.push(await FirebaseMessaging.addListener('notificationReceived', () => heard()))
    held.push(await FirebaseMessaging.addListener('notificationActionPerformed', (e) => {
      opened(e?.notification?.data?.legid || null)
    }))
  } catch { /* texted instead: the server only notifies a phone that has registered */ }
  return () => held.forEach((h) => h.remove())
}

// Signing out: Firebase forgets this phone's token as well as the server.
export async function forgetPhone() {
  if (!native || !PUSH) return
  try {
    const { FirebaseMessaging } = await import('@capacitor-firebase/messaging')
    await FirebaseMessaging.deleteToken()
  } catch { /* the server has already ended it */ }
}
