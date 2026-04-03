import React from 'react';
import { render, screen } from '@testing-library/react-native';
import App from '../App';

describe('App', () => {
  it('renders without crashing', async () => {
    render(<App />);
    expect(screen).toBeTruthy();
  });
});
