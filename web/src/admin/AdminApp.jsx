import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { ReceiptText, Building2, CreditCard, FileBadge, Gauge, Handshake, Landmark, Scale, Users } from 'lucide-react'
import TopBar from '../components/TopBar.jsx'
import Overview from './Overview.jsx'
import Customers from './Customers.jsx'
import CustomerDetail from './CustomerDetail.jsx'
import UsersPage from './Users.jsx'
import CredentialTypes from './CredentialTypes.jsx'
import Brokers from './Brokers.jsx'
import Plans from './Plans.jsx'
import Gateways from './Gateways.jsx'
import FeeSchedule from './FeeSchedule.jsx'
import RuleReview from './RuleReview.jsx'

export default function AdminApp({ user }) {
  const nav = [
    ['Operations', [['/admin', Gauge, 'Overview'], ['/admin/customers', Building2, 'Customers'],
      ['/admin/brokers', Handshake, 'Brokers']]],
    ['Compliance', [['/admin/credentialtypes', FileBadge, 'Document types'],
      ['/admin/rules', Scale, 'Rule review']]],
    ['Reports', []],
    ['Setup', [['/admin/plans', CreditCard, 'Subscription plans'], ['/admin/fees', ReceiptText, 'Fee Schedule'],
      ['/admin/gateways', Landmark, 'Payment gateways'],
      ['/admin/users', Users, 'Users']]],
  ]
  return (
    <div className="app admin">
      <TopBar user={user} admin />
      <div className="shell">
      <nav className="side">
        {nav.map(([section, links]) => (
          <div key={section}>
            <div className="section">{section}</div>
            {links.map(([to, Icon, label]) => (
              <NavLink key={to} to={to} end={to === '/admin'}><Icon size={16} /> {label}</NavLink>
            ))}
          </div>
        ))}
      </nav>
      <main>
        <Routes>
          <Route path="/admin" element={<Overview />} />
          <Route path="/admin/customers" element={<Customers />} />
          <Route path="/admin/customers/:id" element={<CustomerDetail />} />
          <Route path="/admin/users" element={<UsersPage />} />
          <Route path="/admin/credentialtypes" element={<CredentialTypes />} />
          <Route path="/admin/brokers" element={<Brokers />} />
          <Route path="/admin/plans" element={<Plans />} />
          <Route path="/admin/gateways" element={<Gateways />} />
          <Route path="/admin/fees" element={<FeeSchedule />} />
          <Route path="/admin/rules" element={<RuleReview />} />
          <Route path="*" element={<Navigate to="/admin" />} />
        </Routes>
      </main>
      </div>
    </div>
  )
}
